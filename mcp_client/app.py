import streamlit as st
import asyncio
import platform
import nest_asyncio
from client.mcp_client import LawChatClient
from shared.google_auth import login_flow, show_login_button
from shared.db_utils import (
    get_or_create_user,
    create_chat_session,
    update_chat_session_title,
    get_chat_sessions,
    save_conversation,
    load_conversations,
    delete_chat_session
)

from dotenv import load_dotenv

# Windows에서 이벤트 루프 정책 설정
if platform.system() == "Windows":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# 중첩 이벤트 루프 허용
nest_asyncio.apply()

# 이벤트 루프 생성 및 설정
if "event_loop" not in st.session_state:
    loop = asyncio.new_event_loop()
    st.session_state.event_loop = loop
    asyncio.set_event_loop(loop)

st.set_page_config(page_title="LawChat", page_icon="⚖️", layout="centered")
load_dotenv(override=True)


# MCP 클라이언트 캐싱
@st.cache_resource
def get_mcp_client():
    return LawChatClient()


# --- 로그인 페이지 디자인  ---
def show_login_page():
    st.markdown(
        """
    <style>
    .login-container {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100vh;
        text-align: center;
    }
    .login-title {
        font-size: 3rem;
        font-weight: bold;
        color: #1f2937;
        margin-bottom: 1rem;
    }
    .login-subtitle {
        font-size: 1.2rem;
        color: #6b7280;
        margin-bottom: 2rem;
    }
    .login-button {
        background-color: #4285f4;
        color: white;
        padding: 12px 24px;
        border: none;
        border-radius: 8px;
        font-size: 1rem;
        text-decoration: none;
        display: inline-block;
        transition: background-color 0.3s;
    }
    .login-button:hover {
        background-color: #3367d6;
    }
    </style>
    """,
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="login-container">',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="login-title">⚖️ LawChat</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="login-subtitle">법률 상담을 위한 AI 어시스턴트</div>',
        unsafe_allow_html=True
    )

    show_login_button()

    st.markdown(
        '</div>',
        unsafe_allow_html=True
    )


def main():
    # 로그인 확인
    if "user" not in st.session_state:
        if not login_flow():
            show_login_page()
            return

    # 사용자 정보 가져오기
    user_email = st.session_state["user"]["email"]
    user_name = st.session_state["user"]["name"]
    user_id = get_or_create_user(user_email, user_name)

    # 세션 상태 초기화
    if "current_session_id" not in st.session_state:
        st.session_state.current_session_id = None

    # 사이드바: 채팅 히스토리
    with st.sidebar:
        st.header("채팅 히스토리")

        # 새 대화 시작 버튼
        if st.button("➕ 새 대화 시작"):
            session_id = create_chat_session(user_id, "새로운 대화")
            st.session_state.current_session_id = session_id
            st.rerun()

        #세션 목록
        sessions = get_chat_sessions(user_id)
        for session_id, title in sessions:
            col1, col2 = st.columns([3, 1])
            with col1:
                if st.button(f"💬 {title}", key=f"session_{session_id}"):
                    st.session_state.current_session_id = session_id
                    st.rerun()
            with col2:
                if st.button("🗑️", key=f"delete_{session_id}"):
                    delete_chat_session(session_id)
                    if st.session_state.current_session_id == session_id:
                        st.session_state.current_session_id = None
                    st.rerun()

        # 로그아웃 버튼
        if st.button("🚪 로그아웃"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

    # 메인 채팅 인터페이스
    st.title("LawChat")
    st.markdown("법률 질문을 입력하시면 관련 판례를 검색하고 전문적인 답변을 제공해드립니다.")

    # 현재 세션이 없으면 새 세션 생성
    if st.session_state.current_session_id is None:
        session_id = create_chat_session(user_id, "새로운 대화")
        st.session_state.current_session_id = session_id

    #대화 로드 및 표시
    if st.session_state.current_session_id:
        conversations = load_conversations(st.session_state.current_session_id)

        for role, content, timestamp, search_results in conversations:
            if role == "user":
                with st.chat_message("user"):
                    st.write(content)
            else:
                with st.chat_message("assistant"):
                    st.write(content)

                    # 관련 판례 정보 표시
                    if search_results and search_results.get("metadatas"):
                        with st.expander("📚 관련 판례 정보"):
                            for i, metadata in enumerate(search_results["metadatas"]):
                                if isinstance(metadata, dict):
                                    st.write(f"**판례 {i + 1}:**")
                                    if "case_number" in metadata:
                                        st.write(f"- 사건번호: {metadata['case_number']}")
                                    if "court" in metadata:
                                        st.write(f"- 법원: {metadata['court']}")
                                    if "date" in metadata:
                                        st.write(f"- 선고일: {metadata['date']}")
                                    st.write("---")

    # 사용자 입력 처리
    if user_question := st.chat_input("법률 질문을 입력하세요"):
        # 사용자 메시지 표시
        with st.chat_message("user"):
            st.write(user_question)

        # 사용자 메시지 저장
        save_conversation(st.session_state.current_session_id, "user", user_question)

        # MCP 클라이언트를 통한 검색 및 상담
        client = get_mcp_client()

        with st.chat_message("assistant"):
            with st.spinner("판례를 검색하고 분석 중입니다..."):
                result = asyncio.run(client.search_cases(user_question, max_results=3))

            # 분석 결과 표시
            if result and result.get("analysis"):
                st.write(result["analysis"])

                # 관련 판례 정보 표시
                if result.get("metadatas"):
                    with st.expander("📚 관련 판례 정보"):
                        for i, metadata in enumerate(result["metadatas"]):
                            if isinstance(metadata, dict):
                                st.write(f"**판례 {i + 1}:**")
                                if "case_number" in metadata:
                                    st.write(f"- 사건번호: {metadata['case_number']}")
                                if "court" in metadata:
                                    st.write(f"- 법원: {metadata['court']}")
                                if "date" in metadata:
                                    st.write(f"- 선고일: {metadata['date']}")
                                st.write("---")

                # 어시스턴트 응답 저장
                save_conversation(
                    st.session_state.current_session_id,
                    "assistant",
                    result["analysis"],
                    result
                )

                # 세션 제목 업데이트 (첫 번째 질문 기준)
                if len(load_conversations(st.session_state.current_session_id)) == 2:
                    title = user_question[:30] + "..." if len(user_question) > 30 else user_question
                    update_chat_session_title(st.session_state.current_session_id, title)
            else:
                st.error("검색 결과를 가져오는데 실패했습니다.")


if __name__ == "__main__":
    main()

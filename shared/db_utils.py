import streamlit as st
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
import datetime
from sqlalchemy.dialects.mysql import JSON as MySQLJSON
from typing import List, Tuple, Optional, Dict, Any


# --- SQLAlchemy 설정 ---
# 데이터베이스 연결 URL 생성 (st.secrets 사용)
DATABASE_URL = (
    f"mysql+mysqlconnector://{st.secrets['mysql']['user']}:{st.secrets['mysql']['password']}"
    f"@{st.secrets['mysql']['host']}/{st.secrets['mysql']['database']}"
)

# SQLAlchemy 엔진 생성
# pool_recycle: 비활성 연결이 서버 측에서 닫히기 전에 SQLAlchemy가 연결을 재활용하도록 하는 설정
engine = create_engine(DATABASE_URL, pool_recycle=280)

# 세션 생성을 위한 SessionLocal 클래스 정의
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 모든 모델 클래스가 상속할 기본 클래스
Base = declarative_base()


# --- 데이터베이스 모델 정의 ---
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255))

    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False, default="새로운 대화")

    user = relationship("User", back_populates="chat_sessions")
    conversations = relationship("Conversation", back_populates="chat_session", cascade="all, delete-orphan")

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    search_results_json = Column(MySQLJSON, nullable=True)

    chat_session = relationship("ChatSession", back_populates="conversations")

def get_db_session():
    """데이터베이스 세션을 생성하고 제공하는 제너레이터"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_or_create_user(email: str, name: str) -> int:
    """이메일로 사용자를 찾거나 새로 생성하고 사용자 ID를 반환합니다."""
    db = next(get_db_session())
    user = db.query(User).filter(User.email == email).first()
    if user:
        user_id = user.id
    else:
        new_user = User(email=email, name=name)
        db.add(new_user)
        db.commit()
        db.refresh(new_user)
        user_id = new_user.id
    db.close()
    return user_id

def create_chat_session(user_id: int, title: str) -> int:
    """새로운 채팅 세션을 생성하고 세션 ID를 반환합니다."""
    db = next(get_db_session())
    new_session = ChatSession(user_id=user_id, title=title)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    session_id = new_session.id
    db.close()
    return session_id

def update_chat_session_title(session_id: int, title: str):
    """채팅 세션의 제목을 업데이트합니다."""
    db = next(get_db_session())
    session_to_update = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session_to_update:
        session_to_update.title = title
        db.commit()
    db.close()

def get_chat_sessions(user_id: int) -> List[Tuple[int, str]]:
    """특정 사용자의 모든 채팅 세션 (ID, 제목)을 반환합니다."""
    db = next(get_db_session())
    sessions = db.query(ChatSession.id, ChatSession.title)\
                   .filter(ChatSession.user_id == user_id)\
                   .order_by(ChatSession.id)\
                   .all()
    db.close()
    return [(s.id, s.title) for s in sessions]


def save_conversation(session_id: int, role: str, content: str, search_results: Optional[Dict[str, Any]] = None):
    """대화 내용과 (선택적으로) 관련 판례 정보를 저장합니다."""
    db = next(get_db_session())

    search_results_to_save = None
    if search_results and role == "assistant":
        search_results_to_save = search_results

    new_conversation = Conversation(
        session_id=session_id,
        role=role,
        content=content,
        search_results_json=search_results_to_save
    )
    db.add(new_conversation)
    db.commit()
    db.close()


def load_conversations(session_id: int) -> List[Tuple[str, str, datetime.datetime, Optional[Dict[str, Any]]]]:
    """특정 세션의 모든 대화 내용을 (역할, 내용, 타임스탬프, 관련판례정보) 시간 순으로 정렬하여 반환합니다."""
    db = next(get_db_session())
    conversations = db.query(
        Conversation.role,
        Conversation.content,
        Conversation.timestamp,
        Conversation.search_results_json
    ) \
        .filter(Conversation.session_id == session_id) \
        .order_by(Conversation.timestamp) \
        .all()
    db.close()

    results_processed = []
    for conv in conversations:
        role, content, timestamp, sr_json = conv
        results_processed.append((role, content, timestamp, sr_json))

    return results_processed

def delete_chat_session(session_id: int):
    """채팅 세션과 관련된 모든 대화 내용을 삭제합니다."""
    db = next(get_db_session())
    session_to_delete = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if session_to_delete:
        db.delete(session_to_delete)
        db.commit()
    db.close()


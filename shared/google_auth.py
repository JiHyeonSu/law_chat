import streamlit as st
import asyncio
from httpx_oauth.clients.google import GoogleOAuth2
import jwt


client_id = st.secrets["google"]["client_id"]
client_secret = st.secrets["google"]["client_secret"]
redirect_uri = st.secrets["google"]["redirect_uri"]

client = GoogleOAuth2(client_id, client_secret)

def get_full_code():

    codes = st.query_params.get_all("code")

    if codes:
        return codes[0] if len(codes) == 1 else ''.join(codes)
    return ""

def decode_user(token: str):
    return jwt.decode(token, options={"verify_signature": False})

async def get_authorization_url():
    return await client.get_authorization_url(
        redirect_uri,
        scope=["profile", "email"],
        extras_params={"access_type": "offline"},
    )

async def get_access_token(code: str):
    return await client.get_access_token(code, redirect_uri)

async def get_email(token):
    user_id, user_email = await client.get_id_email(token)
    return user_id, user_email

def login_flow():
    code = get_full_code()
    if code:
        if len(code) < 10:
            st.error("OAuth code가 비정상적으로 짧습니다. 인증 플로우를 다시 시작하세요.")
            return False
        loop = get_or_create_eventloop()
        try:
            token = loop.run_until_complete(get_access_token(code))
            user_id, user_email = loop.run_until_complete(get_email(token["access_token"]))
            user_info = decode_user(token["id_token"])
            st.session_state["user"] = {
                "email": user_email,
                "name": user_info.get("name", ""),
                "google_id": user_id,
            }

            st.query_params.clear()
            return True
        except Exception as e:
            st.error(f"Access token 요청 실패: {e}")
            return False
    return False

def show_login_button():
    loop = get_or_create_eventloop()
    authorization_url = loop.run_until_complete(get_authorization_url())
    st.markdown(f'<a href="{authorization_url}">구글 계정으로 로그인</a>', unsafe_allow_html=True)

def get_or_create_eventloop():
    try:
        return asyncio.get_event_loop()
    except RuntimeError as ex:
        if "There is no current event loop in thread" in str(ex):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
        else:
            raise ex

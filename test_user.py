import pytest

from user import router


@pytest.fixture(scope="function")
def client(app_factory, client_factory):
    app = app_factory(router)
    return client_factory(app)


def signup_user(client, email="test@example.com", password="123456", nickname="tester"):
    return client.post(
        "/users/signup",
        json={
            "email": email,
            "password": password,
            "nickname": nickname,
        },
    )


def login_user(client, email="test@example.com", password="123456"):
    return client.post(
        "/users/login",
        json={
            "email": email,
            "password": password,
        },
    )


def get_auth_header(client, email="test@example.com", password="123456"):
    login_response = login_user(client, email=email, password=password)
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ----------------------------
# 회원가입 테스트
# ----------------------------
def test_signup_success(client):
    response = signup_user(client)

    assert response.status_code == 200
    data = response.json()

    assert data["message"] == "signup success"
    assert "user_id" in data
    assert isinstance(data["user_id"], int)
    assert "created_at" in data


def test_signup_duplicate_email_fails(client):
    first = signup_user(client, email="dup@example.com")
    assert first.status_code == 200

    second = signup_user(client, email="dup@example.com")
    assert second.status_code == 400
    assert second.json()["detail"] == "Email already exists"


def test_signup_invalid_password_too_short(client):
    response = signup_user(
        client,
        email="shortpw@example.com",
        password="123",
        nickname="tester",
    )

    assert response.status_code == 422


def test_signup_invalid_nickname_empty(client):
    response = signup_user(
        client,
        email="nonickname@example.com",
        password="123456",
        nickname="",
    )

    assert response.status_code == 422


def test_signup_invalid_nickname_too_long(client):
    response = signup_user(
        client,
        email="longnick@example.com",
        password="123456",
        nickname="a" * 21,
    )

    assert response.status_code == 422


# ----------------------------
# 로그인 테스트
# ----------------------------
def test_login_success_returns_access_token(client):
    signup_user(client, email="login@example.com", password="123456", nickname="loginuser")

    response = login_user(client, email="login@example.com", password="123456")

    assert response.status_code == 200
    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert isinstance(data["access_token"], str)
    assert len(data["access_token"]) > 0


def test_login_wrong_password_fails(client):
    signup_user(client, email="wrongpw@example.com", password="123456", nickname="tester")

    response = login_user(client, email="wrongpw@example.com", password="999999")

    assert response.status_code == 401
    assert response.json()["detail"] == "Email or password is incorrect"


def test_login_nonexistent_user_fails(client):
    response = login_user(client, email="nouser@example.com", password="123456")

    assert response.status_code == 401
    assert response.json()["detail"] == "Email or password is incorrect"


# ----------------------------
# 마이페이지 테스트
# ----------------------------
def test_mypage_requires_auth(client):
    response = client.get("/users/mypage")

    assert response.status_code == 401


def test_mypage_returns_user_info(client):
    signup_user(client, email="mypage@example.com", password="123456", nickname="myuser")
    headers = get_auth_header(client, email="mypage@example.com", password="123456")

    response = client.get("/users/mypage", headers=headers)

    assert response.status_code == 200
    data = response.json()

    assert data["email"] == "mypage@example.com"
    assert data["nickname"] == "myuser"
    assert data["goal_minutes"] == 120
    assert data["default_focus_time"] == 25
    assert data["default_break_time"] == 5
    assert data["experience"] == 0
    assert data["level"] == 1
    assert "created_at" in data


# ----------------------------
# 설정 수정 테스트
# ----------------------------
def test_update_settings_requires_auth(client):
    response = client.put(
        "/users/settings",
        json={
            "goal_minutes": 180,
            "default_focus_time": 50,
            "default_break_time": 10,
        },
    )

    assert response.status_code == 401


def test_update_settings_success(client):
    signup_user(client, email="settings@example.com", password="123456", nickname="setuser")
    headers = get_auth_header(client, email="settings@example.com", password="123456")

    update_response = client.put(
        "/users/settings",
        headers=headers,
        json={
            "goal_minutes": 180,
            "default_focus_time": 50,
            "default_break_time": 10,
        },
    )

    assert update_response.status_code == 200
    assert update_response.json()["message"] == "settings updated"

    mypage_response = client.get("/users/mypage", headers=headers)
    assert mypage_response.status_code == 200

    data = mypage_response.json()
    assert data["goal_minutes"] == 180
    assert data["default_focus_time"] == 50
    assert data["default_break_time"] == 10


def test_update_settings_invalid_value_fails(client):
    signup_user(client, email="invalidsettings@example.com", password="123456", nickname="tester")
    headers = get_auth_header(client, email="invalidsettings@example.com", password="123456")

    response = client.put(
        "/users/settings",
        headers=headers,
        json={
            "goal_minutes": 0,
            "default_focus_time": 50,
            "default_break_time": 10,
        },
    )

    assert response.status_code == 422


def test_update_settings_exceeds_max_value_fails(client):
    signup_user(client, email="maxsettings@example.com", password="123456", nickname="tester")
    headers = get_auth_header(client, email="maxsettings@example.com", password="123456")

    response = client.put(
        "/users/settings",
        headers=headers,
        json={
            "goal_minutes": 1441,
            "default_focus_time": 25,
            "default_break_time": 5,
        },
    )

    assert response.status_code == 422


# ----------------------------
# 닉네임 수정 테스트
# ----------------------------
def test_update_nickname_requires_auth(client):
    response = client.put(
        "/users/nickname",
        json={"nickname": "newnick"},
    )

    assert response.status_code == 401


def test_update_nickname_success(client):
    signup_user(client, email="nickedit@example.com", password="123456", nickname="oldnick")
    headers = get_auth_header(client, email="nickedit@example.com", password="123456")

    response = client.put(
        "/users/nickname",
        headers=headers,
        json={"nickname": "newnick"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "nickname updated"

    mypage_response = client.get("/users/mypage", headers=headers)
    assert mypage_response.json()["nickname"] == "newnick"


def test_update_nickname_empty_fails(client):
    signup_user(client, email="emptynicke@example.com", password="123456", nickname="tester")
    headers = get_auth_header(client, email="emptynicke@example.com", password="123456")

    response = client.put(
        "/users/nickname",
        headers=headers,
        json={"nickname": ""},
    )

    assert response.status_code == 422


def test_update_nickname_too_long_fails(client):
    signup_user(client, email="longnick2@example.com", password="123456", nickname="tester")
    headers = get_auth_header(client, email="longnick2@example.com", password="123456")

    response = client.put(
        "/users/nickname",
        headers=headers,
        json={"nickname": "a" * 21},
    )

    assert response.status_code == 422


# ----------------------------
# 토큰/인증 테스트
# ----------------------------
def test_mypage_with_invalid_token_fails(client):
    response = client.get(
        "/users/mypage",
        headers={"Authorization": "Bearer invalid-token"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"

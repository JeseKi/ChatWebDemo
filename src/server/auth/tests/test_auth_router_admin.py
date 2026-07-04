# -*- coding: utf-8 -*-
from sqlalchemy.orm import Session

from src.server.auth import service
from src.server.auth.models import User
from src.server.auth.schemas import UserRole, UserStatus
from src.server.auth.tests._auth_router_helpers import (
    _auth_headers,
    _auth_headers_with_two_factor,
    _enable_two_factor,
    _login_user,
)


def test_admin_routes_enforce_admin_scopes(test_client, test_db_session):
    admin = User(
        username="scope_admin",
        email="scope_admin@example.com",
        role=UserRole.ADMIN,
    )
    admin.set_password("Password123")
    test_db_session.add(admin)

    user = User(
        username="scope_member",
        email="scope_member@example.com",
        role=UserRole.USER,
    )
    user.set_password("Password123")
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(admin)
    test_db_session.refresh(user)

    user_token = service.create_access_token(
        {"sub": user.username, "scope": service.get_user_scopes(user)}
    )
    user_list_resp = test_client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert user_list_resp.status_code == 403
    assert user_list_resp.json()["detail"]["required_scopes"] == [
        service.SCOPE_ADMIN_USERS_READ
    ]
    assert (
        "admin:users:read"
        in user_list_resp.json()["detail"]["message"]
    )

    forged_user_token = service.create_access_token(
        {
            "sub": user.username,
            "scope": [
                service.SCOPE_ADMIN_USERS_READ,
                service.SCOPE_ADMIN_USERS_WRITE,
            ],
        }
    )
    forged_list_resp = test_client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {forged_user_token}"},
    )
    assert forged_list_resp.status_code == 403
    assert forged_list_resp.json()["detail"]["required_scopes"] == [
        service.SCOPE_ADMIN_USERS_READ
    ]
    assert "admin:users:read" in forged_list_resp.json()["detail"]["message"]

    read_only_admin_token = service.create_access_token(
        {"sub": admin.username, "scope": [service.SCOPE_ADMIN_USERS_READ]}
    )
    list_resp = test_client.get(
        "/api/admin/users",
        headers={"Authorization": f"Bearer {read_only_admin_token}"},
    )
    assert list_resp.status_code == 200, list_resp.text

    patch_resp = test_client.patch(
        f"/api/admin/users/{user.id}",
        json={"name": "Updated by scope"},
        headers={"Authorization": f"Bearer {read_only_admin_token}"},
    )
    assert patch_resp.status_code == 403
    assert patch_resp.json()["detail"]["required_scopes"] == [
        service.SCOPE_ADMIN_USERS_WRITE
    ]
    assert "admin:users:write" in patch_resp.json()["detail"]["message"]

    delete_resp = test_client.delete(
        f"/api/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {read_only_admin_token}"},
    )
    assert delete_resp.status_code == 403
    assert delete_resp.json()["detail"]["required_scopes"] == [
        service.SCOPE_ADMIN_USERS_WRITE
    ]
    assert "admin:users:write" in delete_resp.json()["detail"]["message"]

    write_admin_token = service.create_access_token(
        {
            "sub": admin.username,
            "scope": [
                service.SCOPE_ADMIN_USERS_READ,
                service.SCOPE_ADMIN_USERS_WRITE,
            ],
        }
    )
    updated_resp = test_client.patch(
        f"/api/admin/users/{user.id}",
        json={"name": "Updated by scope"},
        headers={"Authorization": f"Bearer {write_admin_token}"},
    )
    assert updated_resp.status_code == 200, updated_resp.text
    assert updated_resp.json()["name"] == "Updated by scope"

    deleted_resp = test_client.delete(
        f"/api/admin/users/{user.id}",
        headers={"Authorization": f"Bearer {write_admin_token}"},
    )
    assert deleted_resp.status_code == 204, deleted_resp.text
    assert test_db_session.query(User).filter(User.id == user.id).first() is None


def test_admin_can_bulk_update_users(test_client, test_db_session):
    admin = User(
        username="bulk_update_admin",
        email="bulk_update_admin@example.com",
        role=UserRole.ADMIN,
    )
    admin.set_password("Password123")
    member_a = User(
        username="bulk_update_member_a",
        email="bulk_update_member_a@example.com",
        role=UserRole.USER,
    )
    member_a.set_password("Password123")
    member_b = User(
        username="bulk_update_member_b",
        email="bulk_update_member_b@example.com",
        role=UserRole.USER,
    )
    member_b.set_password("Password123")
    test_db_session.add_all([admin, member_a, member_b])
    test_db_session.commit()
    test_db_session.refresh(admin)
    test_db_session.refresh(member_a)
    test_db_session.refresh(member_b)

    admin_token = service.create_access_token(
        {
            "sub": admin.username,
            "scope": [
                service.SCOPE_ADMIN_USERS_READ,
                service.SCOPE_ADMIN_USERS_WRITE,
            ],
        }
    )
    resp = test_client.patch(
        "/api/admin/users/bulk",
        json={
            "user_ids": [member_a.id, member_b.id],
            "role": "admin",
            "status": "inactive",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200, resp.text
    assert [user["id"] for user in resp.json()] == [member_a.id, member_b.id]
    test_db_session.refresh(member_a)
    test_db_session.refresh(member_b)
    assert member_a.role == UserRole.ADMIN
    assert member_b.role == UserRole.ADMIN
    assert member_a.status == UserStatus.INACTIVE
    assert member_b.status == UserStatus.INACTIVE
    assert member_a.token_version == 1
    assert member_b.token_version == 1


def test_admin_can_bulk_delete_users(test_client, test_db_session):
    admin = User(
        username="bulk_delete_admin",
        email="bulk_delete_admin@example.com",
        role=UserRole.ADMIN,
    )
    admin.set_password("Password123")
    member_a = User(
        username="bulk_delete_member_a",
        email="bulk_delete_member_a@example.com",
        role=UserRole.USER,
    )
    member_a.set_password("Password123")
    member_b = User(
        username="bulk_delete_member_b",
        email="bulk_delete_member_b@example.com",
        role=UserRole.USER,
    )
    member_b.set_password("Password123")
    test_db_session.add_all([admin, member_a, member_b])
    test_db_session.commit()
    test_db_session.refresh(admin)
    test_db_session.refresh(member_a)
    test_db_session.refresh(member_b)

    admin_token = service.create_access_token(
        {
            "sub": admin.username,
            "scope": [
                service.SCOPE_ADMIN_USERS_READ,
                service.SCOPE_ADMIN_USERS_WRITE,
            ],
        }
    )
    resp = test_client.request(
        "DELETE",
        "/api/admin/users/bulk",
        json={"user_ids": [member_a.id, member_b.id]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 204, resp.text
    assert test_db_session.query(User).filter(User.id == member_a.id).first() is None
    assert test_db_session.query(User).filter(User.id == member_b.id).first() is None


def test_bulk_user_operations_reject_current_admin(test_client, test_db_session):
    admin = User(
        username="bulk_self_admin",
        email="bulk_self_admin@example.com",
        role=UserRole.ADMIN,
    )
    admin.set_password("Password123")
    test_db_session.add(admin)
    test_db_session.commit()
    test_db_session.refresh(admin)

    admin_token = service.create_access_token(
        {
            "sub": admin.username,
            "scope": [
                service.SCOPE_ADMIN_USERS_READ,
                service.SCOPE_ADMIN_USERS_WRITE,
            ],
        }
    )

    update_resp = test_client.patch(
        "/api/admin/users/bulk",
        json={"user_ids": [admin.id], "status": "inactive"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert update_resp.status_code == 400, update_resp.text
    assert update_resp.json()["detail"] == "不能批量操作当前登录用户"

    delete_resp = test_client.request(
        "DELETE",
        "/api/admin/users/bulk",
        json={"user_ids": [admin.id]},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert delete_resp.status_code == 400, delete_resp.text
    assert delete_resp.json()["detail"] == "不能批量操作当前登录用户"


def test_bulk_update_missing_user_does_not_modify_existing_user(
    test_client, test_db_session
):
    admin = User(
        username="bulk_missing_admin",
        email="bulk_missing_admin@example.com",
        role=UserRole.ADMIN,
    )
    admin.set_password("Password123")
    member = User(
        username="bulk_missing_member",
        email="bulk_missing_member@example.com",
        role=UserRole.USER,
    )
    member.set_password("Password123")
    test_db_session.add_all([admin, member])
    test_db_session.commit()
    test_db_session.refresh(admin)
    test_db_session.refresh(member)

    admin_token = service.create_access_token(
        {
            "sub": admin.username,
            "scope": [
                service.SCOPE_ADMIN_USERS_READ,
                service.SCOPE_ADMIN_USERS_WRITE,
            ],
        }
    )
    resp = test_client.patch(
        "/api/admin/users/bulk",
        json={"user_ids": [member.id, 999999], "role": "admin"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 404, resp.text
    test_db_session.refresh(member)
    assert member.role == UserRole.USER
    assert member.token_version == 0


def test_dangerous_admin_scope_requires_two_factor_when_enabled(
    test_client, test_db_session: Session
):
    admin = User(
        username="danger_admin",
        email="danger_admin@example.com",
        role=UserRole.ADMIN,
    )
    admin.set_password("Password123")
    user = User(
        username="danger_member",
        email="danger_member@example.com",
        role=UserRole.USER,
    )
    user.set_password("Password123")
    test_db_session.add(admin)
    test_db_session.add(user)
    test_db_session.commit()

    login_resp = _login_user(test_client, username="danger_admin")
    secret, _ = _enable_two_factor(
        test_client, access_token=login_resp.json()["access_token"]
    )

    test_client.cookies.clear()
    challenge_resp = test_client.post(
        "/api/auth/login",
        json={"username": "danger_admin", "password": "Password123"},
    )
    verify_resp = test_client.post(
        "/api/auth/2fa/verify",
        json={
            "challenge_token": challenge_resp.json()["challenge_token"],
            "code": service.generate_totp_code(secret),
        },
    )
    access_token = verify_resp.json()["access_token"]

    list_resp = test_client.get(
        "/api/admin/users",
        headers=_auth_headers(access_token),
    )
    assert list_resp.status_code == 200, list_resp.text

    patch_without_2fa = test_client.patch(
        f"/api/admin/users/{user.id}",
        json={"name": "blocked"},
        headers=_auth_headers(access_token),
    )
    assert patch_without_2fa.status_code == 403
    assert patch_without_2fa.json()["detail"] == "危险操作需要二步验证"

    patch_with_2fa = test_client.patch(
        f"/api/admin/users/{user.id}",
        json={"name": "allowed"},
        headers=_auth_headers_with_two_factor(
            access_token, service.generate_totp_code(secret)
        ),
    )
    assert patch_with_2fa.status_code == 200, patch_with_2fa.text
    assert patch_with_2fa.json()["name"] == "allowed"

    bulk_without_2fa = test_client.patch(
        "/api/admin/users/bulk",
        json={"user_ids": [user.id], "status": "inactive"},
        headers=_auth_headers(access_token),
    )
    assert bulk_without_2fa.status_code == 403
    assert bulk_without_2fa.json()["detail"] == "危险操作需要二步验证"

    bulk_with_2fa = test_client.patch(
        "/api/admin/users/bulk",
        json={"user_ids": [user.id], "status": "inactive"},
        headers=_auth_headers_with_two_factor(
            access_token, service.generate_totp_code(secret)
        ),
    )
    assert bulk_with_2fa.status_code == 200, bulk_with_2fa.text
    assert bulk_with_2fa.json()[0]["status"] == "inactive"

def test_admin_cannot_delete_self(test_client, test_db_session):
    admin = User(
        username="self_delete_admin",
        email="self_delete_admin@example.com",
        role=UserRole.ADMIN,
    )
    admin.set_password("Password123")
    test_db_session.add(admin)
    test_db_session.commit()
    test_db_session.refresh(admin)

    admin_token = service.create_access_token(
        {
            "sub": admin.username,
            "scope": [
                service.SCOPE_ADMIN_USERS_READ,
                service.SCOPE_ADMIN_USERS_WRITE,
            ],
        }
    )

    resp = test_client.delete(
        f"/api/admin/users/{admin.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "不能删除当前登录用户"
    assert test_db_session.query(User).filter(User.id == admin.id).first() is not None

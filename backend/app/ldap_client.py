"""OpenLDAP 预留接口。第一期默认关闭，登录走本地账号。"""

from __future__ import annotations


class LdapAuthError(Exception):
    pass


def authenticate_ldap(app, username: str, password: str) -> dict:
    if not app.config.get("LDAP_ENABLED"):
        raise LdapAuthError("LDAP 尚未启用，请使用本地账号登录")

    try:
        import ldap  # type: ignore
    except ImportError as exc:
        raise LdapAuthError("未安装 python-ldap，无法进行 LDAP 认证") from exc

    uri = app.config["LDAP_URI"]
    base_dn = app.config["LDAP_BASE_DN"]
    user_filter = app.config["LDAP_USER_FILTER"].format(username=username)
    conn = ldap.initialize(uri)
    conn.set_option(ldap.OPT_REFERRALS, 0)
    bind_dn = app.config.get("LDAP_BIND_DN")
    bind_pw = app.config.get("LDAP_BIND_PASSWORD")
    if bind_dn:
        conn.simple_bind_s(bind_dn, bind_pw)
    result = conn.search_s(base_dn, ldap.SCOPE_SUBTREE, user_filter, ["uid", "cn", "mail"])
    if not result:
        raise LdapAuthError("LDAP 用户不存在")
    user_dn, attrs = result[0]
    try:
        conn.simple_bind_s(user_dn, password)
    except ldap.INVALID_CREDENTIALS as exc:
        raise LdapAuthError("LDAP 用户名或密码错误") from exc
    uid = (attrs.get("uid") or [username.encode()])[0].decode()
    cn = (attrs.get("cn") or [username.encode()])[0].decode()
    return {"ldap_uid": uid, "display_name": cn, "dn": user_dn}

#!/usr/bin/env python3
import base64
import json
import os
import re
import subprocess
import sys
import time
from collections import deque
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

DOMAIN = "aumara.me"
OLD_IP = "81.88.48.71"
NEW_IP = "213.158.93.19"
LOGIN_URL = "https://controlpanel.nominalia.com/welcome.html"
RUN_ID = os.environ["GITHUB_RUN_ID"]
PUB_PATH = f".secure/nominalia-live-{RUN_ID}.pub"
PASS_PATH = f".secure/nominalia-password-{RUN_ID}.enc"
OTP_PATH = f".secure/nominalia-otp-{RUN_ID}.enc"

DANGEROUS = re.compile(r"logout|salir|delete|remove|borrar|eliminar|cancel|renew|renov|order|pedido|pay|pago|payment|transfer|traspas|titular|invoice|factur|whois|lock|unlock", re.I)
RELEVANT = re.compile(r"aumara\.me|domain|dominio|dns|zona|zone|hosting|alojamiento|gesti|product|producto|record", re.I)
STEPUP = re.compile(r"verification code|c[oó]digo de verificaci[oó]n|one[- ]time|autorizar.*acceso|security code|c[oó]digo.*seguridad", re.I)


def sh(*args, check=True):
    p = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if check and p.returncode:
        raise RuntimeError(f"command failed: {args[0]} ({p.returncode})")
    return p.stdout.strip()


def git_publish(path, message):
    sh("git", "config", "user.name", "github-actions[bot]")
    sh("git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    sh("git", "add", path)
    staged = subprocess.run(["git", "diff", "--cached", "--quiet"]).returncode != 0
    if not staged:
        return
    sh("git", "commit", "-m", message)
    for _ in range(4):
        p = subprocess.run(["git", "push", "origin", "HEAD:main"], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode == 0:
            return
        sh("git", "pull", "--rebase", "origin", "main")
        time.sleep(2)
    raise RuntimeError("unable to publish live public key")


def wait_repo_file(path, timeout):
    deadline = time.time() + timeout
    while time.time() < deadline:
        sh("git", "fetch", "origin", "main", check=False)
        p = subprocess.run(["git", "show", f"origin/main:{path}"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip()
        time.sleep(8)
    raise TimeoutError(f"timed out waiting for {path}")


def decrypt_b64(private_key, payload):
    raw = base64.b64decode(payload)
    return private_key.decrypt(
        raw,
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None),
    ).decode("utf-8").strip()


def soup_of(resp):
    return BeautifulSoup(resp.text, "html.parser")


def form_data(form):
    data = []
    for inp in form.find_all("input"):
        name = inp.get("name")
        if not name:
            continue
        typ = (inp.get("type") or "text").lower()
        if typ in {"submit", "button", "image", "file", "reset"}:
            continue
        if typ in {"checkbox", "radio"} and not inp.has_attr("checked"):
            continue
        data.append((name, inp.get("value", "")))
    for sel in form.find_all("select"):
        name = sel.get("name")
        if not name:
            continue
        opts = sel.find_all("option")
        chosen = next((o for o in opts if o.has_attr("selected")), opts[0] if opts else None)
        if chosen:
            data.append((name, chosen.get("value", chosen.get_text(" ", strip=True))))
    for ta in form.find_all("textarea"):
        if ta.get("name"):
            data.append((ta.get("name"), ta.get_text()))
    return data


def submit(session, base_url, form, data):
    action = urljoin(base_url, form.get("action") or base_url)
    method = (form.get("method") or "get").lower()
    if method == "post":
        return session.post(action, data=data, timeout=40, allow_redirects=True)
    return session.get(action, params=data, timeout=40, allow_redirects=True)


def has_password_form(soup):
    return any(f.find("input", {"type": "password"}) for f in soup.find_all("form"))


def stepup_form(soup):
    page_text = soup.get_text(" ", strip=True)
    if not STEPUP.search(page_text):
        return None
    forms = soup.find_all("form")
    for form in forms:
        visible = [i for i in form.find_all("input") if (i.get("type") or "text").lower() in {"text", "number", "tel"} and i.get("name")]
        if visible:
            return form
    return forms[0] if forms else None


def resolve_stepup(session, resp, private_key):
    soup = soup_of(resp)
    form = stepup_form(soup)
    if not form:
        return resp
    print("OTP_REQUIRED", flush=True)
    encrypted = wait_repo_file(OTP_PATH, 360)
    otp = decrypt_b64(private_key, encrypted)
    data = form_data(form)
    visible = [i for i in form.find_all("input") if (i.get("type") or "text").lower() in {"text", "number", "tel"} and i.get("name")]
    if not visible:
        raise RuntimeError("verification form has no safe code field")
    preferred = next((i for i in visible if re.search(r"code|codigo|c[oó]digo|otp|token|verify|security", i.get("name", ""), re.I)), visible[0])
    name = preferred.get("name")
    data = [(k, otp if k == name else v) for k, v in data]
    if not any(k == name for k, _ in data):
        data.append((name, otp))
    out = submit(session, resp.url, form, data)
    out.raise_for_status()
    if stepup_form(soup_of(out)):
        raise RuntimeError("verification code was not accepted")
    print("OTP_ACCEPTED", flush=True)
    return out


def login(session, private_key, password):
    r = session.get(LOGIN_URL, timeout=40, allow_redirects=True)
    r.raise_for_status()
    soup = soup_of(r)
    form = next((f for f in soup.find_all("form") if f.find("input", {"type": "password"})), None)
    if not form:
        raise RuntimeError("Nominalia login form not found")
    data = form_data(form)
    p = form.find("input", {"type": "password"})
    visible = [i for i in form.find_all("input") if i.get("name") and (i.get("type") or "text").lower() in {"text", "email"}]
    if not p or not visible:
        raise RuntimeError("Nominalia login fields not found")
    user_name = visible[0].get("name")
    pass_name = p.get("name")
    data = [(k, ("admin_elcid" if k == user_name else password if k == pass_name else v)) for k, v in data]
    names = {k for k, _ in data}
    if user_name not in names:
        data.append((user_name, "admin_elcid"))
    if pass_name not in names:
        data.append((pass_name, password))
    out = submit(session, r.url, form, data)
    out.raise_for_status()
    out = resolve_stepup(session, out, private_key)
    s2 = soup_of(out)
    if has_password_form(s2) and "welcome" in urlparse(out.url).path.lower():
        raise RuntimeError("Nominalia control-panel authentication failed")
    print("AUTHENTICATED", flush=True)
    return out


def safe_link(base_url, a):
    href = a.get("href")
    if not href or href.startswith("javascript:") or href.startswith("mailto:"):
        return None
    text = a.get_text(" ", strip=True)
    target = urljoin(base_url, href)
    u = urlparse(target)
    if u.scheme not in {"http", "https"} or u.netloc != "controlpanel.nominalia.com":
        return None
    key = f"{text} {u.path}"
    if DANGEROUS.search(key):
        return None
    if not RELEVANT.search(key):
        return None
    return target


def add_submit_button(form, data, wanted=None):
    buttons = []
    for inp in form.find_all("input"):
        if (inp.get("type") or "").lower() == "submit" and inp.get("name"):
            buttons.append((inp.get("name"), inp.get("value", "")))
    for b in form.find_all("button"):
        if (b.get("type") or "submit").lower() == "submit" and b.get("name"):
            buttons.append((b.get("name"), b.get("value", b.get_text(" ", strip=True))))
    if wanted:
        chosen = next((x for x in buttons if wanted.search(" ".join(x))), None)
        if chosen:
            data.append(chosen)
    elif buttons:
        data.append(buttons[0])
    return data


def try_dns_mutation(session, resp, private_key):
    resp = resolve_stepup(session, resp, private_key)
    soup = soup_of(resp)
    page_text = soup.get_text(" ", strip=True)
    if DOMAIN.lower() not in page_text.lower():
        return None
    for form in soup.find_all("form"):
        old_inputs = [i for i in form.find_all("input") if i.get("name") and i.get("value") == OLD_IP]
        if not old_inputs:
            continue
        if DANGEROUS.search(form.get_text(" ", strip=True)):
            continue
        data = form_data(form)
        targets = {i.get("name") for i in old_inputs}
        changed = 0
        outdata = []
        for k, v in data:
            if k in targets and v == OLD_IP:
                outdata.append((k, NEW_IP)); changed += 1
            else:
                outdata.append((k, v))
        if changed != len(old_inputs):
            raise RuntimeError("refusing ambiguous DNS edit")
        outdata = add_submit_button(form, outdata, re.compile(r"apply|aplicar|save|guardar", re.I))
        print(f"DNS_EDIT_MATCH fields={changed}", flush=True)
        out = submit(session, resp.url, form, outdata)
        out.raise_for_status()
        out = resolve_stepup(session, out, private_key)
        s2 = soup_of(out)
        txt2 = s2.get_text(" ", strip=True)
        # Some Nominalia screens require a final confirmation.
        if NEW_IP in txt2 and re.search(r"confirmar|confirm|continuar|apply changes|aplicar cambios", txt2, re.I):
            for cf in s2.find_all("form"):
                ctext = cf.get_text(" ", strip=True)
                if DANGEROUS.search(ctext):
                    continue
                if re.search(r"confirmar|confirm|continuar|apply|aplicar", ctext, re.I):
                    cdata = add_submit_button(cf, form_data(cf), re.compile(r"confirmar|confirm|continuar|apply|aplicar", re.I))
                    if cdata:
                        out = submit(session, out.url, cf, cdata)
                        out.raise_for_status()
                        out = resolve_stepup(session, out, private_key)
                        break
        print("DNS_MUTATION_SUBMITTED", flush=True)
        return out
    return None


def try_safe_navigation_form(session, resp, private_key):
    soup = soup_of(resp)
    page_text = soup.get_text(" ", strip=True)
    if not re.search(r"dns|dominio|domain", page_text, re.I):
        return None
    wanted = re.compile(r"gestionar dns|gesti[oó]n avanzada|editar zona dns|advanced dns|manage dns|aceptar|accept", re.I)
    for form in soup.find_all("form"):
        ftext = form.get_text(" ", strip=True)
        if DANGEROUS.search(ftext):
            continue
        submit_texts = []
        submit_texts += [i.get("value", "") for i in form.find_all("input") if (i.get("type") or "").lower() == "submit"]
        submit_texts += [b.get_text(" ", strip=True) for b in form.find_all("button")]
        if not wanted.search(" ".join(submit_texts) + " " + ftext):
            continue
        data = add_submit_button(form, form_data(form), wanted)
        if not data:
            continue
        out = submit(session, resp.url, form, data)
        out.raise_for_status()
        return resolve_stepup(session, out, private_key)
    return None


def mutate_dns(session, start, private_key):
    q = deque([(start, 0)])
    seen = set()
    while q and len(seen) < 90:
        resp, depth = q.popleft()
        resp = resolve_stepup(session, resp, private_key)
        key = resp.url.split("#", 1)[0]
        if key in seen:
            continue
        seen.add(key)
        hit = try_dns_mutation(session, resp, private_key)
        if hit is not None:
            return True
        if depth >= 5:
            continue
        soup = soup_of(resp)
        links = []
        for a in soup.find_all("a", href=True):
            u = safe_link(resp.url, a)
            if u and u not in seen:
                links.append(u)
        # Prefer exact domain and DNS routes first.
        links = sorted(dict.fromkeys(links), key=lambda u: (DOMAIN not in u.lower(), "dns" not in u.lower(), len(u)))
        for u in links[:25]:
            try:
                rr = session.get(u, timeout=35, allow_redirects=True)
                rr.raise_for_status()
                rr = resolve_stepup(session, rr, private_key)
                q.append((rr, depth + 1))
            except requests.RequestException:
                continue
        try:
            nav = try_safe_navigation_form(session, resp, private_key)
            if nav is not None:
                q.appendleft((nav, depth + 1))
        except requests.RequestException:
            pass
    return False


def main():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    public_key = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    os.makedirs(os.path.dirname(PUB_PATH), exist_ok=True)
    with open(PUB_PATH, "wb") as f:
        f.write(public_key)
    git_publish(PUB_PATH, f"Publish ephemeral Nominalia key for run {RUN_ID} [skip ci]")
    print(f"PUBLIC_KEY_READY {PUB_PATH}", flush=True)

    encrypted_password = wait_repo_file(PASS_PATH, 360)
    password = decrypt_b64(private_key, encrypted_password)
    print("PASSWORD_RECEIVED_SECURELY", flush=True)

    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 AUMARA authorized Nominalia DNS operator"})
    start = login(session, private_key, password)
    if not mutate_dns(session, start, private_key):
        raise RuntimeError("safe crawler did not find the exact aumara.me A record")
    print(f"DONE {DOMAIN} A {NEW_IP}", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAILED {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise

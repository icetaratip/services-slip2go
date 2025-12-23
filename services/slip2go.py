import json, os, requests

CONFIG = json.load(open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json"), encoding="utf-8"))
SLIP2GO = CONFIG["slip2go"]

def slip2go_verify_file(img: bytes, filename: str) -> dict:
    ct = "image/png" if filename.lower().endswith(".png") else "image/jpeg"

    payload = json.dumps({
        "checkDuplicate": True,
        "checkReceiver": [{
            "accountType": "01004",
            "accountNameTH": SLIP2GO["account_name_th"],
            "accountNameEN": SLIP2GO["account_name_en"],
            "accountNumber": str(SLIP2GO["account_number"])
        }]
    }, ensure_ascii=False, separators=(",",":"))

    r = requests.post(
        f"{SLIP2GO['base_url']}/api/verify-slip/qr-image/info",
        headers={"Authorization": f"Bearer {SLIP2GO['secret_key']}"},
        files={"file": (filename, img, ct), "payload": (None, payload)},
        timeout=30
    )

    if r.status_code not in (200, 201):
        raise Exception(f"Slip2Go HTTP-{r.status_code}: {r.text}")

    try:
        return r.json()
    except:
        raise Exception("Slip2Go invalid JSON")

def parse_slip2go(r: dict):
    d = r.get("data") or {}
    return {
        "code": str(r.get("code")),
        "message": r.get("message"),
        "amount": d.get("amount"),
        "txid": d.get("transRef") or d.get("ref1") or d.get("ref2"),
        "datetime": d.get("dateTime"),
        "sender": d.get("sender", {}).get("account", {}).get("name"),
        "receiver": d.get("receiver", {}).get("account", {}).get("name"),
        "ref_id": d.get("referenceId")
    }

async def process_slip_file(interaction, img: bytes, filename: str,
                            update_user_balance, send_topup_log, add_transaction_history):
    try:
        info = parse_slip2go(slip2go_verify_file(img, filename))
    except Exception as e:
        return await interaction.followup.send(f"❌ {e}", ephemeral=True)

    fail = {
        "200401": "บัญชีผู้รับไม่ถูกต้อง ⚠️",
        "200500": "สลิปปลอม / สลิปเสีย ❌",
        "200501": "สลิปซ้ำ ห้ามใช้ซ้ำ ⚠️"
    }

    code = info["code"]
    if code in fail:
        return await interaction.followup.send(fail[code], ephemeral=True)

    if code not in {"200000", "200001", "200200"}:
        return await interaction.followup.send(
            f"❌ สลิปไม่ถูกต้อง ({info['message']})",
            ephemeral=True
        )

    recv = (info["receiver"] or "").lower()
    th = SLIP2GO["account_name_th"].lower()
    en = SLIP2GO.get("account_name_en", "").lower()

    if not (th in recv or (en and en in recv)):
        expect = SLIP2GO["account_name_th"] + (f" หรือ {SLIP2GO['account_name_en']}" if en else "")
        return await interaction.followup.send(
            f"⚠️ ชื่อบัญชีผู้รับไม่ตรง\nพบ: {info['receiver']}\nต้องเป็น: {expect}",
            ephemeral=True
        )

    if not info["amount"]:
        return await interaction.followup.send("ไม่พบยอดเงินในสลิป", ephemeral=True)

    amount = float(info["amount"])
    uid = interaction.user.id

    update_user_balance(uid, amount)
    add_transaction_history(uid, "slip2go", amount, info)

    await interaction.followup.send(
        f"**เติมเงินสำเร็จ !** ✅\n"
        f"เลขอ้างอิง: `{info['txid']}`\n"
        f"จำนวน: **{amount:,.2f} บาท**\n"
        f"ชื่อผู้โอน: {info['sender'] or '-'}",
        ephemeral=True
    )

    await send_topup_log(interaction.user, amount, info)


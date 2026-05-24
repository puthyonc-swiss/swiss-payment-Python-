"""
main.py
────────
Swiss System Payment Backend (Python)
Uses bakong-khqr Python SDK + RBK Token from Bakong Relay

Endpoints:
  GET  /                      → health check
  POST /api/payment/generate  → generate KHQR
  POST /api/payment/check     → check if payment was made
"""

import os
import time
import urllib.request
import json as _json
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bakong_khqr import KHQR
from dotenv import load_dotenv

load_dotenv()

# ── Config ────────────────────────────────────────────────────
RBK_TOKEN     = os.getenv("RBK_TOKEN", "")
BAKONG_ID     = os.getenv("BAKONG_ID",     "puthyon_chandara@bkrt")
MERCHANT_NAME = os.getenv("MERCHANT_NAME", "Swiss System")
MERCHANT_CITY = os.getenv("MERCHANT_CITY", "Phnom Penh")

# ── ADDED: Firebase Function URL ──────────────────────────────
APPROVE_PAYMENT_URL = "https://approvepayment-dujizfz2la-uc.a.run.app"
BOT_SECRET          = "swisssystem2026"

# ── FastAPI App ───────────────────────────────────────────────
app = FastAPI(title="Swiss System Payment Backend")

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Request Models ────────────────────────────────────────────
class GenerateRequest(BaseModel):
    amount: float = 0.01

class CheckRequest(BaseModel):
    md5: str

# ─────────────────────────────────────────────────────────────
# GET /
# ─────────────────────────────────────────────────────────────
@app.get("/")
def health_check():
    return {
        "status":  "ok",
        "service": "Swiss System Payment Backend (Python)",
        "version": "1.0.0",
    }

# ─────────────────────────────────────────────────────────────
# POST /api/payment/generate
# Body: { "amount": 0.01 }
# Returns: { "success": true, "qr": "...", "md5": "..." }
# ─────────────────────────────────────────────────────────────
@app.post("/api/payment/generate")
def generate_payment(req: GenerateRequest):
    try:
        amount = round(float(req.amount), 2)

        if amount <= 0:
            return {
                "success": False,
                "message": "Invalid amount. Must be greater than 0.",
            }

        khqr        = KHQR(RBK_TOKEN)
        bill_number = f"TRX{int(time.time() * 1000)}"

        qr = khqr.create_qr(
            bank_account=BAKONG_ID,
            merchant_name=MERCHANT_NAME,
            merchant_city=MERCHANT_CITY,
            amount=amount,
            currency="USD",
            bill_number=bill_number,
            store_label="Swiss System",
            terminal_label="Tournament",
            static=False,
        )

        if not qr:
            return {
                "success": False,
                "message": "Failed to generate KHQR.",
            }

        md5 = khqr.generate_md5(qr)
        print(f"✅ KHQR generated | amount: ${amount} | md5: {md5}")

        return {
            "success": True,
            "qr":      qr,
            "md5":     md5,
            "amount":  amount,
        }

    except Exception as e:
        print(f"❌ Generate error: {str(e)}")
        return {
            "success": False,
            "message": f"Internal error: {str(e)}",
        }

# ─────────────────────────────────────────────────────────────
# POST /api/payment/check
# Body: { "md5": "abc123..." }
# Returns: { "success": true, "paid": true/false }
# ─────────────────────────────────────────────────────────────
@app.post("/api/payment/check")
def check_payment(req: CheckRequest):
    try:
        md5 = req.md5.strip()

        if not md5:
            return {
                "success": False,
                "paid":    False,
                "message": "MD5 hash is required.",
            }

        khqr   = KHQR(RBK_TOKEN)
        result = khqr.check_payment(md5)

        print(f"💳 Payment check | md5: {md5} | result: {result}")

        # "UNPAID" = not paid yet
        if result == "UNPAID" or result is None:
            return {
                "success": True,
                "paid":    False,
                "message": "Payment not found yet.",
            }

        # ── ADDED: Save to Firestore when paid ───────────────
        try:
            payer_name = ""
            amount     = 0
            if isinstance(result, dict):
                payer_name = result.get("fromFullName", "") or result.get("payer_name", "") or ""
                amount     = result.get("amount", 0) or 0

            payload = _json.dumps({
                "secret":    BOT_SECRET,
                "txnId":     md5,
                "payerName": payer_name,
                "amount":    amount,
            }).encode("utf-8")
            req_obj = urllib.request.Request(
                APPROVE_PAYMENT_URL,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req_obj, timeout=5) as resp:
                print(f"✅ Saved to Firestore | md5: {md5} | status: {resp.status}")
        except Exception as firebase_err:
            # Do NOT fail payment if Firestore save fails
            print(f"⚠️ Firestore save error: {str(firebase_err)}")
        # ── END ADDED ─────────────────────────────────────────

        return {
            "success": True,
            "paid":    True,
            "message": "Payment confirmed.",
            "data":    result,
        }

    except Exception as e:
        print(f"❌ Check error: {str(e)}")
        return {
            "success": False,
            "paid":    False,
            "message": f"Internal error: {str(e)}",
        }

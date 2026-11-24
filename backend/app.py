from __future__ import annotations
import os
from datetime import datetime, timezone
from functools import wraps
from flask import Flask, jsonify, request, g
from flask_cors import CORS
from backend.assessment_data import BDI2_QUESTIONS, RECOMMENDATIONS
from backend.assessment import create_assessment_document, save_assessment, save_recommendation_feedback
from backend.auth import _public_user, get_request_user, login_user, logout_token, register_user
from backend.database import get_db, ping_database
from backend.training import load_champion
from backend.chatbot import reply_to_message

app=Flask(__name__)
app.config["MAX_CONTENT_LENGTH"]=64*1024
CORS(app,resources={r"/api/*":{"origins":["http://127.0.0.1:5173","http://localhost:5173"]}})

def _token():
    scheme,_,token=request.headers.get("Authorization","").partition(" ")
    return token.strip() if scheme.lower()=="bearer" else None

def require_auth(fn):
    @wraps(fn)
    def wrapped(*args,**kwargs):
        user=get_request_user(request)
        if not user:return jsonify({"error":"Sign in to access this feature."}),401
        g.current_user=user
        return fn(*args,**kwargs)
    return wrapped

def require_admin(fn):
    @wraps(fn)
    @require_auth
    def wrapped(*args,**kwargs):
        admins={x.strip().lower() for x in os.getenv("ADMIN_EMAILS","").split(",") if x.strip()}
        if g.current_user["email"] not in admins:return jsonify({"error":"Administrator access is required."}),403
        return fn(*args,**kwargs)
    return wrapped

@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"]="nosniff"
    response.headers["X-Frame-Options"]="DENY"
    response.headers["Referrer-Policy"]="strict-origin-when-cross-origin"
    if request.path.startswith("/api/"):response.headers["Cache-Control"]="no-store"
    return response

@app.errorhandler(413)
def too_large(_):return jsonify({"error":"Request body is too large."}),413

@app.get("/api/health")
def health():
    try:ping_database();mongo="connected"
    except Exception as exc:mongo=f"unavailable: {type(exc).__name__}"
    meta=None
    if mongo=="connected":
        try:_,meta=load_champion()
        except Exception:app.logger.exception("Model metadata unavailable")
    return jsonify({"api":"ok","mongodb":mongo,"experimental_model":meta or "not yet promoted"})

@app.get("/api/questions")
def questions():return jsonify({"questions":BDI2_QUESTIONS})

@app.post("/api/auth/register")
def auth_register():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return jsonify({"error":"A JSON object is required."}),400
    try:return jsonify(register_user(data.get("name"),data.get("email"),data.get("password"))),201
    except ValueError as exc:return jsonify({"error":str(exc)}),400
    except Exception:
        app.logger.exception("Registration failed");return jsonify({"error":"Could not create the account."}),503

@app.post("/api/auth/login")
def auth_login():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return jsonify({"error":"A JSON object is required."}),400
    try:return jsonify(login_user(data.get("email"),data.get("password")))
    except ValueError as exc:return jsonify({"error":str(exc)}),401
    except Exception:
        app.logger.exception("Login failed");return jsonify({"error":"Could not sign in."}),503

@app.get("/api/auth/me")
@require_auth
def auth_me():return jsonify({"user":_public_user(g.current_user)})

@app.post("/api/auth/logout")
@require_auth
def auth_logout():
    logout_token(_token());return jsonify({"logged_out":True})

@app.post("/api/assessment")
def submit_assessment():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return jsonify({"error":"A JSON object is required."}),400
    storage=data.get("storage_consent",False);research=data.get("research_consent",False)
    if not isinstance(storage,bool) or not isinstance(research,bool):return jsonify({"error":"Consent values must be true or false."}),400
    user=get_request_user(request) if storage else None
    if storage and not user:return jsonify({"error":"Sign in before saving to your personal history."}),401
    try:
        doc=create_assessment_document(data.get("responses"),storage,research,str(user["_id"]) if user else None)
        saved=save_assessment(doc) if storage else None
        level=doc["risk_level"]
        return jsonify({"saved":saved is not None,"feedback_token":doc.get("feedback_token"),
          "total_score":doc["total_score"],"risk_level":level,"recommendations":RECOMMENDATIONS.get(level,{}),
          "self_harm_item_positive":doc["self_harm_item_positive"],
          "safety_guidance":"Your answer suggests speaking promptly with a qualified mental-health professional or trusted person. If you may act on these thoughts or are in immediate danger, contact local emergency services now." if doc["self_harm_item_positive"] else None,
          "notice":"This is a screening result, not a diagnosis. Experimental ML is not used for clinical decisions.",
          "storage_notice":"Saved to your account with consent." if saved else "Not saved; this result is only in this response."}),201
    except (ValueError,TypeError) as exc:return jsonify({"error":str(exc)}),400
    except Exception:
        app.logger.exception("Assessment failed");return jsonify({"error":"Could not process assessment."}),503

@app.get("/api/assessments")
@require_auth
def assessment_history():
    limit=min(max(request.args.get("limit",20,type=int) or 20,1),100)
    docs=get_db()["users"].find({"user_id":str(g.current_user["_id"])},{"total_score":1,"risk_level":1,"created_at":1}).sort("created_at",-1).limit(limit)
    return jsonify({"assessments":[{"id":str(d["_id"]),"total_score":d.get("total_score"),"risk_level":d.get("risk_level"),"created_at":d.get("created_at",datetime.now(timezone.utc)).isoformat()} for d in docs]})

@app.delete("/api/assessments")
@require_auth
def delete_assessments():
    result=get_db()["users"].delete_many({"user_id":str(g.current_user["_id"])})
    return jsonify({"deleted":result.deleted_count,"notice":"Previously trained model artifacts are not automatically unlearned."})

@app.post("/api/assessment/feedback/<feedback_token>/recommendation-feedback")
def recommendation_feedback(feedback_token):
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return jsonify({"error":"A JSON response is required."}),400
    try:save_recommendation_feedback(feedback_token,data.get("followed"));return jsonify({"saved":True})
    except ValueError as exc:return jsonify({"error":str(exc)}),400
    except LookupError as exc:return jsonify({"error":str(exc)}),404
    except Exception:
        app.logger.exception("Feedback save failed");return jsonify({"error":"Could not save feedback."}),503

@app.post("/api/chat")
def chat():
    data=request.get_json(silent=True)
    if not isinstance(data,dict):return jsonify({"error":"A JSON object is required."}),400
    message=data.get("message");save=data.get("save_history",False)
    if not isinstance(message,str) or not message.strip() or len(message)>4000:return jsonify({"error":"Enter a message up to 4000 characters."}),400
    if not isinstance(save,bool):return jsonify({"error":"save_history must be true or false."}),400
    user=get_request_user(request) if save else None
    if save and not user:return jsonify({"error":"Sign in before saving chat history."}),401
    try:
        reply=reply_to_message(message.strip())
        if save:get_db()["chat_history"].insert_one({"user_id":str(user["_id"]),"user_message":message.strip(),"assistant_message":reply,"created_at":datetime.now(timezone.utc),"consent":True})
        return jsonify({"reply":reply,"saved":save})
    except Exception:
        app.logger.exception("Chat failed");return jsonify({"error":"Chat service is unavailable."}),503

@app.get("/api/chat/history")
@require_auth
def chat_history():
    docs=get_db()["chat_history"].find({"user_id":str(g.current_user["_id"])}).sort("created_at",-1).limit(100)
    return jsonify({"messages":[{"user_message":d.get("user_message",""),"assistant_message":d.get("assistant_message",""),"created_at":d.get("created_at",datetime.now(timezone.utc)).isoformat()} for d in docs]})

@app.delete("/api/chat/history")
@require_auth
def delete_chat_history():
    result=get_db()["chat_history"].delete_many({"user_id":str(g.current_user["_id"])})
    return jsonify({"deleted":result.deleted_count})

@app.delete("/api/account")
@require_auth
def delete_account():
    db=get_db();uid=str(g.current_user["_id"])
    db["users"].delete_many({"user_id":uid});db["chat_history"].delete_many({"user_id":uid})
    db["user_sessions"].delete_many({"user_id":g.current_user["_id"]})
    db["user_accounts"].delete_one({"_id":g.current_user["_id"]})
    return jsonify({"deleted":True,"notice":"Stored account data and sessions deleted. Previously trained model artifacts are not automatically unlearned."})

@app.get("/api/admin/analytics")
@require_admin
def admin_analytics():
    col=get_db()["users"]
    levels=list(col.aggregate([{"$group":{"_id":"$risk_level","count":{"$sum":1}}},{"$sort":{"_id":1}}]))
    return jsonify({"total_assessments":col.count_documents({}),"research_consented":col.count_documents({"research_consent":True}),"by_level":[{"level":x["_id"],"count":x["count"]} for x in levels]})

@app.get("/api/model-status")
def model_status():
    try:model,meta=load_champion();return jsonify({"available":model is not None,"metadata":meta})
    except Exception:return jsonify({"available":False,"metadata":None})

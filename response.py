from flask import jsonify


def ok(data: dict | list, status: int = 200):
    return jsonify({"success": True, "data": data, "error": None}), status


def err(message: str, status: int = 400):
    return jsonify({"success": False, "data": None, "error": message}), status

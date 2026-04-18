from app import create_app

app = create_app()

# Health check — Railway pings this to confirm the app is alive
@app.get("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

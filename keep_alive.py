from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route("/")
def home():
    return "Mafia Bot is alive!"

def run():
    app.run(host="0.0.0.0", port=10000)

def keep_alive():
    server = Thread(target=run)
    server.daemon = True
    server.start()

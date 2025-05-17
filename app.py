from flask import Flask, render_template, request, redirect, url_for, session
import json
import os
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "very_secret_key"

CONFIG_PATH = "data/truck_config.json"

def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

truck_data = load_config()
truck_status = {truck["id"]: "available" for truck in truck_data["trucks"]}
logistics_timer = {}
activity_log = []

LOG_PATH = "logs/activity.log"
LOG_RETENTION_HOURS = 72

def log_action(truck_id, new_status):
    os.makedirs("logs", exist_ok=True)
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {truck_id} → {new_status}"
    activity_log.insert(0, entry)

    entries = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r") as f:
            for line in f:
                try:
                    ts_str = line.split("]")[0][1:]
                    ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
                    if (now - ts).total_seconds() <= LOG_RETENTION_HOURS * 3600:
                        entries.append(line.strip())
                except:
                    pass

    entries.append(entry)

    with open(LOG_PATH, "w") as f:
        for line in entries:
            f.write(line + "\n")

@app.route("/")
def index():
    now = datetime.utcnow()
    flash_trucks = []
    logistics_times = {}

    for truck_id, status in truck_status.items():
        if status in ["logistics", "destination"]:
            start_time = logistics_timer.get(truck_id)
            if start_time:
                logistics_times[truck_id] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                if status == "logistics" and now - start_time >= timedelta(minutes=10):
                    flash_trucks.append(truck_id)
                elif status == "destination" and now - start_time >= timedelta(minutes=20):
                    flash_trucks.append(truck_id)

    available_medics = sum(
        1 for truck in truck_data["trucks"]
        if truck["id"].startswith("Medic") and truck_status[truck["id"]] == "available"
    )
    show_admin_alert = available_medics <= 3

    return render_template("index.html",
                           trucks=truck_data["trucks"],
                           status=truck_status,
                           flash_trucks=flash_trucks,
                           logistics_times=logistics_times,
                           activity_log=activity_log,
                           show_admin_alert=show_admin_alert,
                           available_medics=available_medics)


@app.route("/availability", methods=["GET", "POST"])
def availability():
    if request.method == "POST":
        selected = request.form.getlist("available")
        for truck in truck_status:
            if truck_status[truck] not in ["out", "logistics", "destination"]:
                truck_status[truck] = "available" if truck in selected else "unavailable"
                log_action(truck, truck_status[truck])
        return redirect(url_for("index"))

    return render_template("availability.html", trucks=truck_data["trucks"], status=truck_status)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))  # Render sets this env variable
    app.run(host="0.0.0.0", port=port)

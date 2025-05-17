
from flask import Flask, render_template, request, redirect, url_for, session
import json
import os
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)
app.secret_key = "very_secret_key"

CONFIG_PATH = "data/truck_config.json"
truck_data = {}
truck_status = {}
logistics_timer = {}
activity_log = []
LOG_PATH = "logs/activity.log"
LOG_RETENTION_HOURS = 72

def load_config():
    global truck_data, truck_status
    with open(CONFIG_PATH) as f:
        truck_data = json.load(f)
    truck_status = {truck["id"]: "available" for truck in truck_data["trucks"]}

def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)

def log_action(truck_id, new_status):
    os.makedirs("logs", exist_ok=True)
    eastern = pytz.timezone("US/Eastern")  # <-- Use Eastern timezone
    now = datetime.now(eastern)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {truck_id} → {new_status}"
    activity_log.insert(0, entry)

    entries = []
    if os.path.exists(LOG_PATH):
        with open(LOG_PATH, "r") as f:
            for line in f:
                try:
                    ts_str = line.split("]")[0][1:]
                    ts = eastern.localize(datetime.strptime(ts_str, "%m-%d-%y %H:%M:%S"))  # <-- fix here too
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
    flash_trucks = {}
    logistics_times = {}
    for truck_id, status in truck_status.items():
        if status in ["logistics", "destination"]:
            start_time = logistics_timer.get(truck_id)
            if start_time:
                logistics_times[truck_id] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
                if (status == "logistics" and now - start_time >= timedelta(minutes=10)) or                    (status == "destination" and now - start_time >= timedelta(minutes=20)):
                    flash_trucks[truck_id] = True

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

@app.route("/dispatch", methods=["POST"])
def dispatch():
    truck_id = request.form["truck_id"]
    truck_status[truck_id] = "out"
    log_action(truck_id, "out")
    fallback_id = None
    for rule in truck_data["fallback_rules"]:
        if rule["primary"] == truck_id:
            for candidate in rule.get("fallbacks", []):
                if truck_status.get(candidate) == "available":
                    fallback_id = candidate
                    break
            break
    return render_template("result.html", dispatched=truck_id, fallback=fallback_id)

@app.route("/reset/<truck_id>")
@app.route("/reset_logistics/<truck_id>")
@app.route("/reset_destination/<truck_id>")
def reset_status(truck_id):
    truck_status[truck_id] = "available"
    logistics_timer.pop(truck_id, None)
    log_action(truck_id, "available")
    return redirect(url_for("index"))

@app.route("/logistics/<truck_id>")
def make_logistics(truck_id):
    truck_status[truck_id] = "logistics"
    logistics_timer[truck_id] = datetime.utcnow()
    log_action(truck_id, "logistics")
    return redirect(url_for("index"))

@app.route("/destination/<truck_id>")
def make_destination(truck_id):
    truck_status[truck_id] = "destination"
    logistics_timer[truck_id] = datetime.utcnow()
    log_action(truck_id, "destination")
    return redirect(url_for("index"))

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

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("logged_in"):
        if request.method == "POST" and request.form.get("password") == "ADMIN123":
            session["logged_in"] = True
            return redirect("/admin")
        return render_template("admin_login.html")
    if request.method == "POST":
        for truck in truck_data["trucks"]:
            new_loc = request.form.get(f"location_{truck['id']}")
            if new_loc:
                truck["location"] = new_loc
        new_rules = []
        for truck in truck_data["trucks"]:
            fb_val = request.form.get(f"fallback_{truck['id']}", "")
            fb_list = [x.strip() for x in fb_val.split(",") if x.strip()]
            new_rules.append({"primary": truck["id"], "fallbacks": fb_list})
        truck_data["fallback_rules"] = new_rules
        save_config(truck_data)
    fallback_map = {rule["primary"]: ", ".join(rule["fallbacks"]) for rule in truck_data["fallback_rules"]}
    return render_template("admin.html", trucks=truck_data["trucks"], fallback_map=fallback_map)

if __name__ == "__main__":
    load_config()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

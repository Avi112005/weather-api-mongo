import os
import certifi
import requests
from flask import Flask, render_template, request
from pymongo import MongoClient
from dotenv import load_dotenv

# -------------------------
# Load Environment Variables
# -------------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

# -------------------------
# MongoDB Atlas Connection
# -------------------------
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise RuntimeError("MONGO_URI not set in .env")

client = MongoClient(
    mongo_uri,
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=5000
)

# Verify connection
client.admin.command("ping")

db = client["weather_db"]
collection = db["weather_data"]

# -------------------------
# Routes
# -------------------------

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        city = request.form.get("city", "").strip()

        if not city:
            return "Invalid city name."

        # 1️⃣ Get coordinates using Open-Meteo Geocoding API
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1"
        geo_response = requests.get(geo_url)

        if geo_response.status_code != 200:
            return "Geocoding API error."

        geo_data = geo_response.json()

        if "results" not in geo_data:
            return "City not found."

        result = geo_data["results"][0]
        lat = result["latitude"]
        lon = result["longitude"]
        city_name = result["name"]
        country = result.get("country", "")

        # 2️⃣ Fetch current + hourly weather
        weather_url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&hourly=temperature_2m"
        )

        weather_response = requests.get(weather_url)

        if weather_response.status_code != 200:
            return "Weather API error."

        weather_data = weather_response.json()

        if "current_weather" not in weather_data:
            return "Weather data unavailable."

        current = weather_data["current_weather"]
        hourly = weather_data.get("hourly", {})

        # Take first 5 hourly values for display
        hourly_times = hourly.get("time", [])[:5]
        hourly_temps = hourly.get("temperature_2m", [])[:5]

        weather = {
            "city": city_name,
            "country": country,
            "temperature": current["temperature"],
            "wind_speed": current["windspeed"],
            "timestamp": current["time"],
            "hourly_preview": list(zip(hourly_times, hourly_temps))
        }

        # 3️⃣ Store in MongoDB
        collection.insert_one(weather)

        return render_template("result.html", weather=weather)

    return render_template("index.html")


@app.route("/history")
def history():
    records = list(
        collection.find({}, {"_id": 0}).sort("_id", -1).limit(10)
    )
    return render_template("history.html", records=records)


# -------------------------
# Run Application
# -------------------------
if __name__ == "__main__":
    app.run()
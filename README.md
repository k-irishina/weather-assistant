# weather-assistant v0.1

Designed to check the weather forecast so you don't have to (and for me to work with Python).

### Main features
* Provides a short forecast and recommendations based on the weather conditions
* Sends periodic updates on forecast changes (currently only for sunny and wet conditions)

### How to use
Message @WhisperWeatherBot on Telegram and use /help to get available commands and set up your experience.

### Upcoming features
* More accurate predictions
* Automatic short forecast sent at user-defined time
* A more detailed forecast upon user request
* Recommendations based on past weather and the forecast
* Better-looking output
* Standalone app for UI and notifications

### Tech

The app is written in Python. User interaction and notifications are currently provided through a Telegram bot, with plans to eventually create a standalone application, but the current focus is accurate data analysis. Database used is PostgreSQL.

All forecast data is kindly provided by [MET Weather API](https://api.met.no/)

#### TODOs
* Fix timezone inaccuracy
* Introduce tests
* Store all forecast data in one INSERT statement
* Better determination of sunny conditions
* Remove pytz
* Logging, not printing

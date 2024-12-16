from app import app, auto_update

with app.app_context():
    auto_update()
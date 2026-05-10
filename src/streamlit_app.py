import os
import sys

# Запускаем основное приложение из корня проекта
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(root)
sys.path.insert(0, root)

exec(open(os.path.join(root, "streamlit_app.py")).read())

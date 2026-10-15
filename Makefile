.PHONY: install test db-up refresh dashboard compose-up clean

install:
	python3 -m pip install -e '.[dev]'

test:
	pytest

db-up:
	docker compose up -d db

refresh:
	financial-analysis refresh --companies all

dashboard:
	streamlit run app/streamlit_app.py --server.port 8502

compose-up:
	docker compose up --build -d db dashboard

clean:
	find . -type d -name __pycache__ -prune -exec rm -r {} +
	find . -type d -name .pytest_cache -prune -exec rm -r {} +

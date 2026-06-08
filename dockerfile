FROM python:3.12-slim

WORKDIR /app
#컨테이너 안에서 작업폴더 /app으로 지정함. 앞으로의 현재폴더(.)

COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install --no-cache -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
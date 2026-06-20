IMAGE := aegis-home

.PHONY: install sync build up down logs shell

install sync:
	uv sync

build:
	docker build -t $(IMAGE) .

up:
	docker run --rm -it \
		--env-file .env \
		-p 8000:8000 \
		$(IMAGE)

down:
	docker stop $$(docker ps -q --filter ancestor=$(IMAGE)) 2>/dev/null || true

logs:
	docker logs -f $$(docker ps -q --filter ancestor=$(IMAGE))

shell:
	docker run --rm -it \
		--env-file .env \
		--entrypoint /bin/sh \
		$(IMAGE)

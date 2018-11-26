
TARGET_ENV ?= dev

COMPOSE_FILE ?= docker-compose.yml
ifeq ($(TARGET_ENV),dev)
	COMPOSE_FILE := $(COMPOSE_FILE):dc-dev.yml
endif

DISTUTILS_DEBUG=1
 
export

all: dc-build dc-up

test:
	python setup.py test $(A)
	
dc-%:
	docker-compose $* $(A)

dc-test:
	make dc-run A='postal make test'

dc-test-%:
	make dc-run A='postal make test A="-s postal.tests.$*"'

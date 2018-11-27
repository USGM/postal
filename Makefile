
TARGET_ENV ?= dev

COMPOSE_FILE ?= docker-compose.yml
COMPOSE_FILE := $(COMPOSE_FILE):dc-$(TARGET_ENV).yml

DOCKER_REGISTRY ?= registry.usglobalmail.com:5000
DISTUTILS_DEBUG ?= 1
TAG ?= $(shell git rev-parse --short HEAD)

export

all: dc-build dc-test

test:
	python setup.py test $(A)
	
dc-%:
	docker-compose $* $(A)

dc-test:
	make dc-run A='postal make test TARGET_ENV=$(TARGET_ENV)'

dc-test-%:
	make dc-run A='postal make test A="-s postal.tests.$*"'


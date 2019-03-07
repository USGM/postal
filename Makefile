
TARGET_ENV ?= dev

COMPOSE_FILE ?= docker-compose.yml
COMPOSE_FILE := $(COMPOSE_FILE):dc-$(TARGET_ENV).yml

DOCKER_REGISTRY ?= docker-registry.usglobalmail.com:5000
DISTUTILS_DEBUG ?= 1
TAG ?= $(shell git rev-parse --short HEAD)
SWARM_ADDR ?= 192.168.20.62:2376
VAULT_SKIP_VERIFY ?= true
VAULT_ROLE_NAME ?= integrator
VAULT_ADDR ?= https://vault.usglobalmail.com

export

all: dc-build dc-test

all-swarm: dc-build dc-push swarm-test


test:
	python setup.py test $(A)
	
dc-%:
	docker-compose $* $(A)

dc-test:
	make dc-run A='postal make test TARGET_ENV=$(TARGET_ENV)'

dc-test-%:
	make dc-run A='postal make test A="-s postal.tests.$*"'
	
swarm-test: DOCKER_HOST=$(SWARM_ADDR)
swarm-test:
	-docker service rm postal-$(TAG)
	docker service create --name postal-$(TAG) -d --restart-condition=none \
		-e VAULT_ADDR=https://vault.usglobalmail.com \
		-e VAULT_AUTH_CONF=/run/secrets/vault_auth.yml \
		--with-registry-auth --secret vault_auth.yml \
		$(DOCKER_REGISTRY)/postal:$(TAG) 
	docker service logs -f postal-$(TAG)
	docker service rm postal-$(TAG)
	
secret: DOCKER_HOST=$(SWARM_ADDR)
secret:
	-docker secret rm vault_auth.yml
	docker secret create vault_auth.yml ./.vault_auth.yml
	
.vault_auth.yml:
	ROLE_ID=`vault read -field=role_id auth/approle/role/${VAULT_ROLE_NAME}/role-id` \
	SECRET_ID=`vault write -field=secret_id -f auth/approle/role/${VAULT_ROLE_NAME}/secret-id` \
    eval "echo \"$$(cat vault_auth.tmpl.yml)\"" > .vault_auth.yml


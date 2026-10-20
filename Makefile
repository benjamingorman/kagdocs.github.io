.DEFAULT_GOAL := all

DOCKER ?= docker
DOCS_IMAGE ?= kagdocs-builder:local
SERVER_IMAGE ?= nginx:1.28.0-alpine
DOCS_CONTAINER ?= kagdocs-local
DOCS_DIR ?= $(CURDIR)/build/docs
DOCS_PORT ?= 8080
DOCS_CONTEXT ?= 5
SYMBOL ?= *
-include docs.local.mk

ifeq ($(OS),Windows_NT)
KAG_DIR ?= C:/Program Files (x86)/Steam/steamapps/common/King Arthur's Gold
else
KAG_DIR ?= $(HOME)/.local/share/Steam/steamapps/common/King Arthur's Gold
endif

.PHONY: all build image host-docs stop-docs test check-docs scaffold
# A recipe dependency enforces build-before-host even under make -j.
all: build
	$(MAKE) host-docs

image:
	$(DOCKER) build -t $(DOCS_IMAGE) .

build: image
	$(DOCKER) run --rm --mount "type=bind,source=$(KAG_DIR),target=/kag,readonly" --mount "type=bind,source=$(CURDIR),target=/workspace" $(DOCS_IMAGE) kagdocs build --kag-dir /kag --output "$(DOCS_DIR)" --host-root "$(CURDIR)" --context-lines $(DOCS_CONTEXT)

# The builder image only writes files. nginx serves build/docs; a later build
# shows up immediately because the directory stays mounted.
host-docs:
	-$(DOCKER) rm -f $(DOCS_CONTAINER)
	$(DOCKER) run -d --name $(DOCS_CONTAINER) -p 127.0.0.1:$(DOCS_PORT):80 --mount "type=bind,source=$(DOCS_DIR),target=/usr/share/nginx/html,readonly" $(SERVER_IMAGE)
	@echo Docs: http://localhost:$(DOCS_PORT)

stop-docs:
	-$(DOCKER) rm -f $(DOCS_CONTAINER)

test: image
	$(DOCKER) run --rm $(DOCS_IMAGE) kagdocs test

check-docs: image
	$(DOCKER) run --rm --mount "type=bind,source=$(CURDIR),target=/workspace,readonly" $(DOCS_IMAGE) kagdocs check --output "$(DOCS_DIR)" --host-root "$(CURDIR)"

scaffold: image
	$(DOCKER) run --rm --mount "type=bind,source=$(KAG_DIR),target=/kag,readonly" --mount "type=bind,source=$(CURDIR)/docs,target=/app/docs" $(DOCS_IMAGE) kagdocs scaffold --kag-dir /kag --symbol "$(SYMBOL)"

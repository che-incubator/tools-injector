# Container tool detection (follows DWO pattern)
ifneq ($(shell command -v docker 2>/dev/null),)
  DOCKER := docker
  BUILDX_AVAILABLE := $(shell docker buildx version >/dev/null 2>&1 && echo true || echo false)
else ifneq ($(shell command -v podman 2>/dev/null),)
  DOCKER := podman
  BUILDX_AVAILABLE := false
else
  $(error No container tool found. Install docker or podman)
endif

# Image registry
IMAGE_REGISTRY ?= quay.io/che-incubator

# Tool definitions
TOOLS := opencode goose claude-code kilocode gemini-cli tmux python3

# Default tag
TAG ?= next

# Helper to derive image name from tool name
_IMG = $(IMAGE_REGISTRY)/tools-injector/$1:$(TAG)

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_%-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-30s\033[0m %s\n", $$1, $$2}'

# ==============================================================================
# Internal per-arch build targets (not shown in help)
# ==============================================================================

_docker-build-%-amd64:
ifeq ($(DOCKER),docker)
  ifeq ($(BUILDX_AVAILABLE),false)
	$(error Docker buildx is required for platform-specific builds. Please update Docker or enable buildx)
  endif
	$(DOCKER) buildx build --platform linux/amd64 --load \
		-f dockerfiles/$*/Dockerfile \
		-t $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-amd64 .
else
	$(DOCKER) build --platform linux/amd64 \
		-f dockerfiles/$*/Dockerfile \
		-t $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-amd64 .
endif

_docker-build-%-arm64:
ifeq ($(DOCKER),docker)
  ifeq ($(BUILDX_AVAILABLE),false)
	$(error Docker buildx is required for platform-specific builds. Please update Docker or enable buildx)
  endif
	$(DOCKER) buildx build --platform linux/arm64 --load \
		-f dockerfiles/$*/Dockerfile \
		-t $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-arm64 .
else
	$(DOCKER) build --platform linux/arm64 \
		-f dockerfiles/$*/Dockerfile \
		-t $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-arm64 .
endif

# ==============================================================================
# Per-tool targets
# ==============================================================================

.PHONY: docker-build-%
docker-build-%: ## Build multi-arch (amd64+arm64) images locally, no push (e.g., make docker-build-opencode)
	@echo "Building multi-arch images for $* using $(DOCKER)"
ifeq ($(DOCKER),docker)
	$(MAKE) _docker-build-$*-amd64 _docker-build-$*-arm64
	@echo "Built multi-arch images locally:"
	@echo "  $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-amd64"
	@echo "  $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-arm64"
	@echo "Note: Manifest list will be created during push to registry"
else
	$(MAKE) _docker-build-$*-amd64 _docker-build-$*-arm64
	@echo "Creating manifest list for $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) using Podman"
	@echo "Cleaning up any existing images/manifests with the same name"
	@$(DOCKER) manifest rm $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) 2>/dev/null || echo "    (manifest not found, continuing)"
	@$(DOCKER) rmi $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) 2>/dev/null || echo "    (image not found, continuing)"
	$(DOCKER) manifest create $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) \
		$(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-amd64 \
		$(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-arm64
endif

.PHONY: docker-push-%
docker-push-%: ## Push per-arch images and create manifest list (e.g., make docker-push-opencode)
	@echo "Pushing multi-arch image $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) using $(DOCKER)"
ifeq ($(DOCKER),docker)
  ifeq ($(BUILDX_AVAILABLE),false)
	$(error Docker buildx is required for multi-arch pushes. Please update Docker or enable buildx)
  endif
	@echo "Using Docker buildx to push multi-arch image"
	$(DOCKER) push $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-amd64
	$(DOCKER) push $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-arm64
	@echo "Creating and pushing manifest list using Docker buildx"
	$(DOCKER) buildx imagetools create -t $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) \
		$(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-amd64 \
		$(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-arm64
else
	@echo "Using Podman to push multi-arch image"
	$(DOCKER) push $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-amd64
	$(DOCKER) push $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-arm64
	@echo "Cleaning up any existing manifests before recreating"
	@$(DOCKER) manifest rm $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) 2>/dev/null || echo "    (manifest not found, continuing)"
	$(DOCKER) manifest create $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) \
		$(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-amd64 \
		$(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)-arm64
	$(DOCKER) manifest push $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG)
endif

.PHONY: docker-%
docker-%: ## Build and push multi-arch image (shorthand) (e.g., make docker-opencode)
	$(MAKE) docker-build-$*
	$(MAKE) docker-push-$*

.PHONY: docker-build-local-%
docker-build-local-%: ## Build for current platform only — quick local testing (e.g., make docker-build-local-opencode)
	$(DOCKER) build -f dockerfiles/$*/Dockerfile \
		-t $(IMAGE_REGISTRY)/tools-injector/$*:$(TAG) .

# ==============================================================================
# Aggregate targets
# ==============================================================================

.PHONY: docker-build-all
docker-build-all: $(addprefix docker-build-,$(TOOLS)) ## Build all tool images (multi-arch, no push)

.PHONY: docker-push-all
docker-push-all: $(addprefix docker-push-,$(TOOLS)) ## Push all tool images (multi-arch)

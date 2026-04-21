# Variables
PROJECT_ID = cs5260-travel-agent
REGION = asia-southeast1
REPO_NAME = travel-agent-repo
IMAGE_TAG = 1.0.0

# Computed Variables
REGISTRY_URL = $(REGION)-docker.pkg.dev/$(PROJECT_ID)/$(REPO_NAME)
FRONTEND_IMAGE_NAME = frontend
BACKEND_IMAGE_NAME = backend

.PHONY: all build build-frontend build-backend tag tag-frontend tag-backend push push-frontend push-backend deploy

all: deploy

# ==========================================
# BUILD COMMANDS
# ==========================================
build: build-frontend build-backend

build-frontend:
	@echo "Building Frontend Image..."
	docker build --platform linux/amd64 -t $(FRONTEND_IMAGE_NAME) ./frontend

build-backend:
	@echo "Building Backend Image..."
	docker build --platform linux/amd64 -t $(BACKEND_IMAGE_NAME) ./backend

# ==========================================
# TAG COMMANDS
# ==========================================
tag: tag-frontend tag-backend

tag-frontend:
	@echo "Tagging Frontend Image..."
	docker tag $(FRONTEND_IMAGE_NAME) $(REGISTRY_URL)/$(FRONTEND_IMAGE_NAME):$(IMAGE_TAG)

tag-backend:
	@echo "Tagging Backend Image..."
	docker tag $(BACKEND_IMAGE_NAME) $(REGISTRY_URL)/$(BACKEND_IMAGE_NAME):$(IMAGE_TAG)

# ==========================================
# PUSH COMMANDS
# ==========================================
push: push-frontend push-backend

push-frontend:
	@echo "Pushing Frontend Image..."
	docker push $(REGISTRY_URL)/$(FRONTEND_IMAGE_NAME):$(IMAGE_TAG)

push-backend:
	@echo "Pushing Backend Image..."
	docker push $(REGISTRY_URL)/$(BACKEND_IMAGE_NAME):$(IMAGE_TAG)

frontend: build-frontend tag-frontend push-frontend
	@echo "Successfully built, tagged, and pushed frontend images to $(REGISTRY_URL)"

backend: build-backend tag-backend push-backend
	@echo "Successfully built, tagged, and pushed backend images to $(REGISTRY_URL)"

# ==========================================
# FULL DEPLOY WORKFLOW
# ==========================================
deploy: build tag push
	@echo "Successfully built, tagged, and pushed all images to $(REGISTRY_URL)"

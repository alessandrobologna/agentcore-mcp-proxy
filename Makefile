PROJECT ?= agentcore-proxy-demo-server
ECR_REPO_NAME ?= $(PROJECT)
TAG ?= latest
STACK_NAME ?= agentcore-proxy-demo-server
AGENT_RUNTIME_NAME ?= agentcore_proxy_demo_server
TEMPLATE ?= template.yaml
PLATFORM ?= linux/arm64

REGION ?= $(AWS_REGION)
ifeq ($(strip $(REGION)),)
REGION := $(AWS_DEFAULT_REGION)
endif
ifeq ($(strip $(REGION)),)
REGION := $(shell aws configure get region 2>/dev/null)
endif
ifeq ($(strip $(REGION)),)
$(error REGION is not set. Pass REGION=..., set AWS_REGION/AWS_DEFAULT_REGION, or configure an AWS CLI default region.)
endif

ACCOUNT_ID := $(shell aws sts get-caller-identity --query Account --output text)
REGISTRY := $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com
LOCAL_IMAGE := $(PROJECT)-local:$(TAG)
ECR_IMAGE_LATEST := $(REGISTRY)/$(ECR_REPO_NAME):$(TAG)

.PHONY: help all build push deploy ecr-login ensure-repo outputs clean

.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

all: deploy ## Build, push, and deploy everything

build: ## Build the Docker image locally
	docker buildx build --platform $(PLATFORM) -t $(LOCAL_IMAGE) --load ./server

ensure-repo:
	@if ! aws ecr describe-repositories --repository-names $(ECR_REPO_NAME) --region $(REGION) >/dev/null 2>&1; then \
		echo "Creating ECR repository $(ECR_REPO_NAME) in $(REGION)"; \
		aws ecr create-repository --repository-name $(ECR_REPO_NAME) --region $(REGION); \
	fi

ecr-login:
	aws ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $(REGISTRY)

push: build ensure-repo ecr-login ## Build and push Docker image to ECR
	docker tag $(LOCAL_IMAGE) $(ECR_IMAGE_LATEST)
	docker push $(ECR_IMAGE_LATEST)
	@IMAGE_DIGEST=$$(docker image inspect --format='{{.Id}}' $(LOCAL_IMAGE) | sed 's|^sha256:||'); \
	IMAGE_URI=$(REGISTRY)/$(ECR_REPO_NAME):sha256-$${IMAGE_DIGEST}; \
	docker tag $(LOCAL_IMAGE) $${IMAGE_URI}; \
	docker push $${IMAGE_URI}; \
	echo "Published $${IMAGE_URI}"

deploy: push ## Build, push, and deploy to AWS (SAM stack)
	@IMAGE_DIGEST=$$(docker image inspect --format='{{.Id}}' $(LOCAL_IMAGE) | sed 's|^sha256:||'); \
	IMAGE_URI=$(REGISTRY)/$(ECR_REPO_NAME):sha256-$${IMAGE_DIGEST}; \
	sam deploy \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--template-file $(TEMPLATE) \
		--capabilities CAPABILITY_IAM \
		--parameter-overrides ContainerImageURI=$${IMAGE_URI} AgentRuntimeName=$(AGENT_RUNTIME_NAME)

outputs: ## Show CloudFormation stack outputs
	aws cloudformation describe-stacks --stack-name $(STACK_NAME) --region $(REGION) --query 'Stacks[0].Outputs'

smoke-test: ## Run smoke test against deployed runtime
	@if [ -z "$(AGENTCORE_AGENT_ARN)" ]; then \
		echo "Getting Agent ARN from stack outputs..."; \
		export AGENTCORE_AGENT_ARN=$$(aws cloudformation describe-stacks --stack-name $(STACK_NAME) --region $(REGION) --query 'Stacks[0].Outputs[?OutputKey==`AgentRuntimeArn`].OutputValue' --output text); \
		uv run scripts/proxy_smoketest.py "$$AGENTCORE_AGENT_ARN" --proxy-cmd uv run src/mcp_agentcore_proxy/cli.py; \
	else \
		uv run scripts/proxy_smoketest.py "$(AGENTCORE_AGENT_ARN)" --proxy-cmd uv run src/mcp_agentcore_proxy/cli.py; \
	fi

clean: ## Remove local Docker images
	-docker rmi $(LOCAL_IMAGE) >/dev/null 2>&1 || true
	-docker rmi $(ECR_IMAGE_LATEST) >/dev/null 2>&1 || true

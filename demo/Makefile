PROJECT ?= agentcore-proxy-demo
ECR_REPO_NAME ?= $(PROJECT)
TAG ?= latest
STACK_NAME ?= agentcore-proxy-demo-servers
STATELESS_AGENT_RUNTIME_NAME ?= agentcore_proxy_stateless
STATEFUL_AGENT_RUNTIME_NAME ?= agentcore_proxy_stateful
TEMPLATE ?= agentcore/template.yaml
PLATFORM ?= linux/arm64

REGION ?= $(AWS_REGION)
ifeq ($(strip $(REGION)),)
REGION := $(AWS_DEFAULT_REGION)
endif
ifeq ($(strip $(REGION)),)
REGION := $(shell aws --no-cli-pager configure get region 2>/dev/null)
endif
ifeq ($(strip $(REGION)),)
$(error REGION is not set. Pass REGION=..., set AWS_REGION/AWS_DEFAULT_REGION, or configure an AWS CLI default region.)
endif

ACCOUNT_ID := $(shell aws --no-cli-pager sts get-caller-identity --query Account --output text)
REGISTRY := $(ACCOUNT_ID).dkr.ecr.$(REGION).amazonaws.com
STATELESS_LOCAL_IMAGE := $(PROJECT)-stateless-local:$(TAG)
STATEFUL_LOCAL_IMAGE := $(PROJECT)-stateful-local:$(TAG)
STATELESS_ECR_IMAGE := $(REGISTRY)/$(ECR_REPO_NAME):stateless-$(TAG)
STATEFUL_ECR_IMAGE := $(REGISTRY)/$(ECR_REPO_NAME):stateful-$(TAG)

STATELESS_DIGEST_TAG_PREFIX := stateless-sha256-
STATEFUL_DIGEST_TAG_PREFIX := stateful-sha256-

.PHONY: help all build build-stateless build-stateful push deploy ecr-login ensure-repo outputs clean smoke-test smoke-test-stateless smoke-test-stateful

.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

all: deploy ## Build, push, and deploy everything

build: build-stateless build-stateful ## Build both Docker images locally

build-stateless:
	@docker buildx build --platform $(PLATFORM) -t $(STATELESS_LOCAL_IMAGE) --load -f agentcore/runtime_stateless/Dockerfile ..

build-stateful:
	@docker buildx build --platform $(PLATFORM) -t $(STATEFUL_LOCAL_IMAGE) --load -f agentcore/runtime_stateful/Dockerfile ..

ensure-repo:
	@if ! aws --no-cli-pager ecr describe-repositories --repository-names $(ECR_REPO_NAME) --region $(REGION) >/dev/null 2>&1; then \
		echo "Creating ECR repository $(ECR_REPO_NAME) in $(REGION)"; \
		aws --no-cli-pager ecr create-repository --repository-name $(ECR_REPO_NAME) --region $(REGION); \
	fi

ecr-login:
	aws --no-cli-pager ecr get-login-password --region $(REGION) | docker login --username AWS --password-stdin $(REGISTRY)

push: build ensure-repo ecr-login ## Build and push Docker images to ECR
	# Stateless image
	@docker tag $(STATELESS_LOCAL_IMAGE) $(STATELESS_ECR_IMAGE)
	@docker push $(STATELESS_ECR_IMAGE)
	@STATELESS_DIGEST=$$(docker image inspect --format='{{.Id}}' $(STATELESS_LOCAL_IMAGE) | sed 's|^sha256:||'); \
	STATELESS_DIGEST_URI=$(REGISTRY)/$(ECR_REPO_NAME):$(STATELESS_DIGEST_TAG_PREFIX)$${STATELESS_DIGEST}; \
	docker tag $(STATELESS_LOCAL_IMAGE) $$STATELESS_DIGEST_URI; \
	docker push $$STATELESS_DIGEST_URI; \
	echo "Published $$STATELESS_DIGEST_URI"; \
	# Stateful image
	@docker tag $(STATEFUL_LOCAL_IMAGE) $(STATEFUL_ECR_IMAGE)
	@docker push $(STATEFUL_ECR_IMAGE)
	@STATEFUL_DIGEST=$$(docker image inspect --format='{{.Id}}' $(STATEFUL_LOCAL_IMAGE) | sed 's|^sha256:||'); \
	STATEFUL_DIGEST_URI=$(REGISTRY)/$(ECR_REPO_NAME):$(STATEFUL_DIGEST_TAG_PREFIX)$${STATEFUL_DIGEST}; \
	docker tag $(STATEFUL_LOCAL_IMAGE) $$STATEFUL_DIGEST_URI; \
	docker push $$STATEFUL_DIGEST_URI; \
	echo "Published $$STATEFUL_DIGEST_URI"; \
	echo "Stateless image tag: $(STATELESS_ECR_IMAGE)"; \
	echo "Stateful image tag: $(STATEFUL_ECR_IMAGE)"

deploy: push ## Build, push, and deploy to AWS (SAM stack)
	@STATELESS_DIGEST=$$(docker image inspect --format='{{.Id}}' $(STATELESS_LOCAL_IMAGE) | sed 's|^sha256:||'); \
	STATEFUL_DIGEST=$$(docker image inspect --format='{{.Id}}' $(STATEFUL_LOCAL_IMAGE) | sed 's|^sha256:||'); \
	STATELESS_IMAGE_URI=$(REGISTRY)/$(ECR_REPO_NAME):$(STATELESS_DIGEST_TAG_PREFIX)$${STATELESS_DIGEST}; \
	STATEFUL_IMAGE_URI=$(REGISTRY)/$(ECR_REPO_NAME):$(STATEFUL_DIGEST_TAG_PREFIX)$${STATEFUL_DIGEST}; \
	sam deploy \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--template-file $(TEMPLATE) \
		--capabilities CAPABILITY_IAM \
		--parameter-overrides \
			LogLevel=DEBUG \
			StatelessContainerImageURI=$${STATELESS_IMAGE_URI} \
			StatefulContainerImageURI=$${STATEFUL_IMAGE_URI} \
			StatelessAgentRuntimeName=$(STATELESS_AGENT_RUNTIME_NAME) \
			StatefulAgentRuntimeName=$(STATEFUL_AGENT_RUNTIME_NAME)

outputs: ## Show CloudFormation stack outputs
	@aws --no-cli-pager cloudformation describe-stacks --stack-name $(STACK_NAME) --region $(REGION) --query 'Stacks[0].Outputs'

smoke-test: smoke-test-stateless smoke-test-stateful ## Run both stateless and stateful smoketests

smoke-test-stateless: ## Run smoketest against deployed stateless runtime
	@if [ -z "$(AGENTCORE_AGENT_ARN)" ]; then \
		echo "Getting stateless Agent ARN from stack outputs..."; \
		AGENTCORE_AGENT_ARN=$$(aws --no-cli-pager cloudformation describe-stacks --stack-name $(STACK_NAME) --region $(REGION) --query 'Stacks[0].Outputs[?OutputKey==`StatelessAgentRuntimeArn`].OutputValue' --output text); \
		AGENTCORE_AGENT_ARN=$$AGENTCORE_AGENT_ARN uv run scripts/proxy_smoketest.py "$$AGENTCORE_AGENT_ARN" --proxy-cmd uv run ../src/mcp_agentcore_proxy/client.py; \
	else \
		AGENTCORE_AGENT_ARN=$(AGENTCORE_AGENT_ARN) uv run scripts/proxy_smoketest.py "$(AGENTCORE_AGENT_ARN)" --proxy-cmd uv run ../src/mcp_agentcore_proxy/client.py; \
	fi

smoke-test-stateful: ## Run smoketest against deployed stateful runtime
	@if [ -z "$(AGENTCORE_AGENT_ARN)" ]; then \
		echo "Getting stateful Agent ARN from stack outputs..."; \
		AGENTCORE_AGENT_ARN=$$(aws --no-cli-pager cloudformation describe-stacks --stack-name $(STACK_NAME) --region $(REGION) --query 'Stacks[0].Outputs[?OutputKey==`StatefulAgentRuntimeArn`].OutputValue' --output text); \
		AGENTCORE_AGENT_ARN=$$AGENTCORE_AGENT_ARN RUNTIME_SESSION_MODE=session uv run scripts/proxy_smoketest.py "$$AGENTCORE_AGENT_ARN" --mode stateful --proxy-cmd uv run ../src/mcp_agentcore_proxy/client.py; \
	else \
		AGENTCORE_AGENT_ARN=$(AGENTCORE_AGENT_ARN) RUNTIME_SESSION_MODE=session uv run scripts/proxy_smoketest.py "$(AGENTCORE_AGENT_ARN)" --mode stateful --proxy-cmd uv run ../src/mcp_agentcore_proxy/client.py; \
	fi

clean: ## Remove local Docker images
	-docker rmi $(STATELESS_LOCAL_IMAGE) >/dev/null 2>&1 || true
	-docker rmi $(STATEFUL_LOCAL_IMAGE) >/dev/null 2>&1 || true
	-docker rmi $(STATELESS_ECR_IMAGE) >/dev/null 2>&1 || true
	-docker rmi $(STATEFUL_ECR_IMAGE) >/dev/null 2>&1 || true

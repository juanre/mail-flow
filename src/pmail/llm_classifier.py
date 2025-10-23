# ABOUTME: LLM-based email classification using workflow context and examples
# ABOUTME: Builds prompts from workflow definitions and past classifications

import logging
from typing import Any

from llmring import LLMRequest, LLMRing, Message

from pmail.models import CriteriaInstance, WorkflowDefinition

logger = logging.getLogger(__name__)


class WorkflowClassification:
    """
    Result from LLM-based email classification.

    Attributes:
        workflow: Name of the suggested workflow
        confidence: Confidence score (0.0 to 1.0)
        reasoning: Explanation of why this workflow was chosen
    """

    def __init__(self, workflow: str, confidence: float, reasoning: str):
        self.workflow = workflow
        self.confidence = confidence
        self.reasoning = reasoning


class LLMClassifier:
    """Classify emails using LLM with workflow context"""

    # Constants
    BODY_PREVIEW_LENGTH = 300  # Maximum characters from email body in prompt

    # JSON schema for structured output
    CLASSIFICATION_SCHEMA = {
        "type": "object",
        "properties": {
            "workflow": {
                "type": "string",
                "description": "Name of the workflow that should process this email",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Confidence score (0.0 to 1.0)",
            },
            "reasoning": {
                "type": "string",
                "description": "Brief explanation of why this workflow was chosen",
            },
        },
        "required": ["workflow", "confidence", "reasoning"],
    }

    def __init__(self, model_alias: str = "balanced"):
        """
        Initialize LLM classifier.

        Args:
            model_alias: llmring model alias (fast, balanced, deep)
        """
        self.model_alias = model_alias
        self._service = None

    async def __aenter__(self):
        """Context manager entry"""
        self._service = LLMRing()
        await self._service.__aenter__()
        return self

    async def __aexit__(self, *args):
        """Context manager exit"""
        if self._service:
            await self._service.__aexit__(*args)

    async def classify(
        self,
        email_data: dict[str, Any],
        workflows: dict[str, WorkflowDefinition],
        criteria_instances: list[CriteriaInstance],
        max_examples_per_workflow: int = 3,
    ) -> WorkflowClassification:
        """
        Classify email using LLM with workflow context.

        Args:
            email_data: Extracted email data
            workflows: Available workflows
            criteria_instances: Past classifications for context
            max_examples_per_workflow: Max examples to include per workflow

        Returns:
            WorkflowClassification with suggested workflow and confidence
        """
        prompt = self._build_prompt(
            email_data, workflows, criteria_instances, max_examples_per_workflow
        )

        request = LLMRequest(
            model=self.model_alias,
            messages=[Message(role="user", content=prompt)],
            temperature=0.3,  # Lower for consistency
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "workflow_classification", "schema": self.CLASSIFICATION_SCHEMA},
                "strict": True,
            },
        )

        try:
            response = await self._service.chat(request)

            if response.parsed:
                result = response.parsed
                workflow_name = result["workflow"]

                # Validate workflow exists
                if workflow_name not in workflows:
                    logger.error(f"LLM suggested invalid workflow: {workflow_name}")
                    raise ValueError(
                        f"LLM suggested non-existent workflow '{workflow_name}'. "
                        f"Available workflows: {', '.join(workflows.keys())}"
                    )

                logger.info(
                    f"LLM classified as '{workflow_name}' "
                    f"(confidence: {result['confidence']:.2f})"
                )
                return WorkflowClassification(
                    workflow=result["workflow"],
                    confidence=result["confidence"],
                    reasoning=result["reasoning"],
                )
            else:
                logger.error("LLM response parsing failed")
                raise ValueError("Failed to parse LLM response")

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            raise

    def _sanitize_for_prompt(self, text: str, max_length: int = 500) -> str:
        """Sanitize text for safe inclusion in LLM prompt"""
        if not text:
            return ""

        # Truncate
        text = text[:max_length]

        # Remove any potentially malicious characters/sequences
        # Remove null bytes
        text = text.replace('\x00', '')
        # Remove excessive newlines
        text = ' '.join(text.split())

        return text

    def _build_prompt(
        self,
        email_data: dict[str, Any],
        workflows: dict[str, WorkflowDefinition],
        criteria_instances: list[CriteriaInstance],
        max_examples: int,
    ) -> str:
        """Build classification prompt with all context"""

        prompt = """You are an email classification assistant for pmail.

Your task: Suggest which workflow should process this email based on workflow definitions and past examples.

Available workflows:
"""

        # Group criteria instances by workflow
        workflow_examples = {}
        for instance in criteria_instances:
            if instance.workflow_name not in workflow_examples:
                workflow_examples[instance.workflow_name] = []
            workflow_examples[instance.workflow_name].append(instance)

        # Add each workflow with its examples
        for name, workflow in workflows.items():
            prompt += f"\n**{name}**\n"
            prompt += f"  Description: {workflow.description}\n"
            prompt += f"  Action: {workflow.action_type}\n"

            # Add directory if relevant
            if "directory" in workflow.action_params:
                prompt += f"  Directory: {workflow.action_params['directory']}\n"

            # Add examples for this workflow
            examples = workflow_examples.get(name, [])[:max_examples]
            if examples:
                prompt += "  Past examples:\n"
                for ex in examples:
                    features = ex.email_features
                    prompt += f"    - From: {features.get('from_domain', 'unknown')}\n"
                    subject_words = features.get("subject_words", [])[:5]
                    if subject_words:
                        prompt += f"      Subject: {', '.join(subject_words)}\n"
                    if features.get("has_pdf"):
                        prompt += "      Has PDF attachment\n"

        # Add the current email to classify
        prompt += f"""

Email to classify:
  From: {self._sanitize_for_prompt(email_data['from'], 200)}
  Subject: {self._sanitize_for_prompt(email_data['subject'], 200)}
  Has PDF: {email_data['features']['has_pdf']}
  Has attachments: {email_data['features']['has_attachments']}
  Body preview: {self._sanitize_for_prompt(email_data['body'], self.BODY_PREVIEW_LENGTH)}...

Based on the workflow definitions and past examples, which workflow should process this email?

Respond with:
- workflow: The exact workflow name from the list above
- confidence: A score from 0.0 to 1.0
- reasoning: A brief explanation (1-2 sentences) of why this workflow matches
"""

        return prompt

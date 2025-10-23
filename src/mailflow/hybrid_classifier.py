# ABOUTME: Hybrid classifier combining similarity-based and LLM classification
# ABOUTME: Routes to appropriate classifier based on confidence thresholds

import logging
from typing import TYPE_CHECKING, Any

from mailflow.models import CriteriaInstance, WorkflowDefinition
from mailflow.similarity import SimilarityEngine

if TYPE_CHECKING:
    from mailflow.llm_classifier import LLMClassifier

logger = logging.getLogger(__name__)


class HybridClassifier:
    """
    Hybrid email classification using confidence-based routing.

    Combines similarity-based and LLM-based classification for optimal
    accuracy and cost efficiency:

    - High confidence (≥ 0.85): Uses similarity only (fast, free)
    - Medium confidence (0.50-0.85): Offers LLM assist (shows both)
    - Low confidence (< 0.50): Uses LLM as primary (most accurate)

    The classifier tracks statistics for each routing path and falls back
    gracefully if LLM is unavailable or fails.

    Args:
        similarity_engine: SimilarityEngine for pattern matching
        llm_classifier: Optional LLMClassifier for AI-powered classification

    Attributes:
        stats: Dictionary tracking usage of each classification method
    """

    # Confidence thresholds
    HIGH_CONFIDENCE = 0.85  # Auto-accept similarity result
    MEDIUM_CONFIDENCE = 0.50  # Offer LLM assist (between medium and high)
    # Below MEDIUM_CONFIDENCE: Use LLM as primary

    def __init__(
        self, similarity_engine: SimilarityEngine, llm_classifier: "LLMClassifier | None" = None
    ):
        """
        Initialize hybrid classifier.

        Args:
            similarity_engine: Existing SimilarityEngine
            llm_classifier: Optional LLMClassifier instance
        """
        self.similarity_engine = similarity_engine
        self.llm_classifier = llm_classifier
        self.stats = {"similarity_only": 0, "llm_only": 0, "llm_assisted": 0}

    async def classify(
        self,
        email_data: dict[str, Any],
        workflows: dict[str, WorkflowDefinition],
        criteria_instances: list[CriteriaInstance],
        use_llm: bool = True,
    ) -> dict[str, Any]:
        """
        Classify email using hybrid approach.

        Args:
            email_data: Extracted email data
            workflows: Available workflows
            criteria_instances: Past criteria instances
            use_llm: Whether to use LLM (can be disabled)

        Returns:
            dict with:
                - rankings: List of (workflow, score, instances) tuples
                - method: "similarity", "llm", "hybrid", or "similarity_fallback"
                - llm_suggestion: Optional LLM classification
        """
        # 1. Try similarity engine first
        rankings = self.similarity_engine.rank_workflows(
            email_data["features"], criteria_instances, top_n=5
        )

        result = {"rankings": rankings, "method": "similarity", "llm_suggestion": None}

        # If no LLM available or disabled, return similarity results
        if not use_llm or not self.llm_classifier:
            self.stats["similarity_only"] += 1
            return result

        # 2. Check confidence level
        if rankings:
            top_confidence = rankings[0][1]

            if top_confidence >= self.HIGH_CONFIDENCE:
                # High confidence - use similarity only
                self.stats["similarity_only"] += 1
                logger.info(f"High confidence ({top_confidence:.0%}) - using similarity")
                return result

            elif top_confidence >= self.MEDIUM_CONFIDENCE:
                # Medium confidence - get LLM suggestion but show both
                logger.info(f"Medium confidence ({top_confidence:.0%}) - offering LLM assist")
                try:
                    async with self.llm_classifier:
                        llm_result = await self.llm_classifier.classify(
                            email_data, workflows, criteria_instances
                        )
                    result["llm_suggestion"] = llm_result
                    result["method"] = "hybrid"
                    self.stats["llm_assisted"] += 1
                except Exception as e:
                    logger.warning(f"LLM assist failed: {e}")
                    # Fall back to similarity only
                return result

        # 3. Low/no confidence - use LLM primary classification
        logger.info("Low confidence - using LLM classification")
        try:
            async with self.llm_classifier:
                llm_result = await self.llm_classifier.classify(
                    email_data, workflows, criteria_instances
                )

            # Convert LLM result to ranking format for consistency
            result["rankings"] = [(llm_result.workflow, llm_result.confidence, [])]
            result["llm_suggestion"] = llm_result
            result["method"] = "llm"
            self.stats["llm_only"] += 1

        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            # Fall back to similarity rankings
            result["method"] = "similarity_fallback"

        return result

    def get_stats(self) -> dict[str, int]:
        """Get classification statistics"""
        return self.stats.copy()

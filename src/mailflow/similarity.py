# ABOUTME: Similarity scoring as a fast pre-filter before LLM classification.
# ABOUTME: Uses weighted Jaccard similarity on email features (domain, subject, attachments).
# ABOUTME:
# ABOUTME: Role in the classification pipeline:
# ABOUTME:   1. Similarity check (fast, local, free)
# ABOUTME:   2. If score < min_threshold: skip email - not relevant to any workflow
# ABOUTME:   3. If score >= skip_llm_threshold (98%): accept similarity result directly
# ABOUTME:   4. Otherwise: send to LLM (llm-archivist) for proper classification
# ABOUTME:
# ABOUTME: This avoids LLM costs for obviously irrelevant emails.
from typing import Any


class SimilarityEngine:
    """Calculate similarity between emails based on their features"""

    def __init__(self, config):
        self.config = config
        self.feature_weights = config.settings["feature_weights"]

    def calculate_similarity(
        self, email_features: dict[str, Any], criteria_instance: "CriteriaInstance"
    ) -> float:
        """Calculate similarity score between current email and a criteria instance"""

        similarities = {}

        # Domain similarity (exact match or not)
        if "from_domain" in self.feature_weights:
            similarities["from_domain"] = float(
                email_features.get("from_domain", "")
                == criteria_instance.email_features.get("from_domain", "")
            )

        # Subject similarity (Jaccard similarity of word sets)
        if "subject_similarity" in self.feature_weights:
            current_words = set(email_features.get("subject_words", []))
            criteria_words = set(criteria_instance.email_features.get("subject_words", []))
            similarities["subject_similarity"] = self._jaccard_similarity(
                current_words, criteria_words
            )

        # PDF attachment similarity
        if "has_pdf" in self.feature_weights:
            similarities["has_pdf"] = float(
                email_features.get("has_pdf", False)
                == criteria_instance.email_features.get("has_pdf", False)
            )

        # Body keywords similarity
        if "body_keywords" in self.feature_weights:
            current_body = set(email_features.get("body_preview_words", []))
            criteria_body = set(criteria_instance.email_features.get("body_preview_words", []))
            similarities["body_keywords"] = self._jaccard_similarity(current_body, criteria_body)

        # To address similarity
        if "to_address" in self.feature_weights:
            current_to = email_features.get("to", "").lower()
            criteria_to = criteria_instance.email_features.get("to", "").lower()
            similarities["to_address"] = float(current_to == criteria_to)

        # Calculate weighted average
        total_score = 0
        total_weight = 0

        for feature, score in similarities.items():
            weight = self.feature_weights.get(feature, 0)
            total_score += score * weight
            total_weight += weight

        if total_weight == 0:
            return 0

        base_score = total_score / total_weight

        # No time-based weighting - all criteria are equally valid regardless of age
        # Older criteria may even be more valuable as they've proven useful over time

        return base_score

    def _jaccard_similarity(self, set1: set, set2: set) -> float:
        """Calculate Jaccard similarity between two sets"""
        if not set1 and not set2:
            return 1.0
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def rank_workflows(
        self,
        email_features: dict[str, Any],
        criteria_instances: list["CriteriaInstance"],
        top_n: int = 5,
    ) -> list[tuple[str, float, list["CriteriaInstance"]]]:
        """Rank workflows based on similarity to past criteria instances"""

        workflow_scores = {}
        workflow_instances = {}

        # Calculate scores for each workflow based on its criteria instances
        for instance in criteria_instances:
            score = self.calculate_similarity(email_features, instance)
            workflow = instance.workflow_name

            if workflow not in workflow_scores:
                workflow_scores[workflow] = []
                workflow_instances[workflow] = []

            workflow_scores[workflow].append(score)
            workflow_instances[workflow].append((score, instance))

        # Aggregate scores for each workflow
        workflow_rankings = []

        for workflow, scores in workflow_scores.items():
            # Use max score, but could also use mean or other aggregation
            max_score = max(scores)

            # Get the best matching instances
            sorted_instances = sorted(
                workflow_instances[workflow], key=lambda x: x[0], reverse=True
            )
            best_instances = [inst for _, inst in sorted_instances[:3]]

            workflow_rankings.append((workflow, max_score, best_instances))

        # Sort by score
        workflow_rankings.sort(key=lambda x: x[1], reverse=True)

        return workflow_rankings[:top_n]

    def get_feature_explanation(
        self, email_features: dict[str, Any], criteria_instance: "CriteriaInstance"
    ) -> dict[str, str]:
        """Explain why an email matches a criteria instance"""

        explanations = {}

        if email_features.get("from_domain") == criteria_instance.email_features.get(
            "from_domain"
        ):
            explanations["from_domain"] = (
                f"Same sender domain: {email_features.get('from_domain')}"
            )

        current_words = set(email_features.get("subject_words", []))
        criteria_words = set(criteria_instance.email_features.get("subject_words", []))
        common_words = current_words & criteria_words
        if common_words:
            explanations["subject"] = f"Similar subject words: {', '.join(list(common_words)[:5])}"

        if email_features.get("has_pdf") and criteria_instance.email_features.get("has_pdf"):
            explanations["attachments"] = "Both have PDF attachments"

        return explanations

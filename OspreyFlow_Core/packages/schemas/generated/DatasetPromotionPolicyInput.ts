// AUTO-GENERATED — do not edit by hand.
// Source: packages/schemas/domain.py, analytics.py, ingest.py, profile.py, model.py and compute.py, via generate_ts.py
export type PromotionPolicy = "author_promotes" | "second_person_reviews";

/**
 * `PUT /v1/admin/datasets/{dataset_id}/promotion-policy`: an administrator's change,
 * audited.
 */
export interface DatasetPromotionPolicyInput {
  promotion_policy: PromotionPolicy;
}

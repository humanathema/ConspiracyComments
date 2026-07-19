# data/processed Manifest

Generated on 2026-07-20 by systematically cross-referencing every processed data file against the active and archived notebooks and scripts.

## File Statuses
- **ACTIVE** — explicitly read or written by the active [ConspiracyMaster_Refactored.ipynb](file:///Users/nash/Projects/ConspiracyComments/ConspiracyMaster_Refactored.ipynb) or production modules in `src/`.
- **legacy** — referenced only by historical/archived notebooks (retained for research provenance and lineage trace).
- **orphan** — not referenced in any active or historical codebase; candidates for safe cleanup.

| File | Size | Modified | Status | Columns (first 8) |
|---|---|---|---|---|
| Academic Record (1).png | 1.5 MB | 2026-06-21 | orphan |  |
| MUdetails.csv | 0.0 MB | 2026-06-21 | orphan | link_id, post_title, post_url, comment_text, comment_score |
| STRATIFIED_SAMPLE_appeal_to_authority.csv | 0.0 MB | 2026-06-22 | legacy (Untitled1.ipynb) | id, category, upvotes, human_verdict, notes, tagged_spans, full_text |
| STRATIFIED_SAMPLE_procedural_skepticism.csv | 0.0 MB | 2026-06-22 | legacy (Untitled1.ipynb) | id, category, upvotes, human_verdict, notes, tagged_spans, full_text |
| STRATIFIED_SAMPLE_source_citation.csv | 0.0 MB | 2026-06-22 | legacy (Untitled1.ipynb) | id, category, upvotes, human_verdict, notes, tagged_spans, full_text |
| anti_establishment_stanceresults.csv | 1.5 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_isolated, label_v2_multi, passes_seen, passes_positive, agreement_score |
| api_audit_sampling_1k.parquet | 0.0 MB | 2026-06-18 | ACTIVE (master notebook) | link_id,true_high_traction_count,strata |
| appeal_to_authority_candidates.csv | 6.0 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, text, hitl_label |
| appeal_to_authority_tuned_endpoint_classified.csv | 6.0 MB | 2026-06-22 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, target_text, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority, procedural_skepticism |
| appeal_to_authorityresults.csv | 1.3 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_lite, label_flash, label_pro, label_v2_multi, passes_seen |
| askreddit_regression_results.csv | 0.0 MB | 2026-07-15 | legacy | model, type, variable, coef, se, pvalue, n_obs |
| attp.csv | 0.1 MB | 2026-06-21 | ACTIVE (master notebook) | title, domain, score, num_comments, upvote_ratio |
| attributed.csv | 250.2 MB | 2026-06-20 | ACTIVE (master notebook) | text, upvotes, controversiality, attribution_class |
| attribution_scorer_validation_sample.csv | 0.1 MB | 2026-07-15 | legacy | entity, sentence, confidence, pattern_type, pattern_text, competing_entity, accusation_conflict |
| attributions.csv | 0.0 MB | 2026-06-20 | orphan | , attribution_class, n, pct |
| author_crawl_queue.csv | 12.5 MB | 2026-06-22 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, r_conspiracy_comments |
| author_insider_metrics.csv | 25.8 MB | 2026-07-14 | legacy | author, conspiracy_comments, conspiracy_ratio, z_log_conspiracy_comments, z_conspiracy_ratio, lexical_insider_score, z_lexical_insider_score, mean_alignment_score |
| author_spam_bot_flags.parquet | 13.0 MB | 2026-07-18 | ACTIVE (master notebook) | author,spam_flag,bot_flag |
| author_subreddit_footprints.csv | 6.5 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, subreddit, comment_count |
| author_subreddit_footprints_async.csv | 196.0 MB | 2026-06-22 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, subreddit, comment_count |
| bertopic_model | 726.2 MB | 2026-06-17 | ACTIVE (master notebook) |  |
| breakouts.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | title, score, num_comments, num_crossposts, upvote_ratio, permalink |
| brigade_test.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | upvote_tier, total_comments, avg_controversiality, expertise_talk_percentage |
| candidates_10k_embedded.parquet | 23.1 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id,embeddings |
| cascade_anti_establishment_stance.csv | 1.4 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| cascade_appeal_to_authority.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| cascade_final_classifications.csv | 1.7 MB | 2026-06-22 | legacy (03_Semantic_Classification.ipynb) | id, target_text, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority, procedural_skepticism |
| cascade_hedged_suspicion.csv | 1.3 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| cascade_insider_ethos.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| cascade_maverick_authority.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| cascade_personal_experience.csv | 1.3 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| cascade_procedural_skepticism.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| cascade_reasonableness_performance.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| cascade_source_citation.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, target_text, pass1_lite, pass2_flash, pass3_pro, cascade_outcome, final_spans |
| census_ordered_targets.parquet | 1.5 MB | 2026-06-18 | legacy (ConspiracyMaster_mechanical_clean.ipynb) | id,target |
| classifier_performance_summary.csv | 0.0 MB | 2026-07-06 | legacy | dimension, measure, n_human, base_rate, kappa, precision, recall, f1 |
| clean.csv | 120.7 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, body, created_utc, id, extracted_span, span_length, word_count |
| combined_human_scores.csv | 0.1 MB | 2026-06-23 | legacy (async_llm_scraper.ipynb) | row_idx, hedged_suspicion_score, hedged_suspicion_source, anti_establishment_stance_score, anti_establishment_stance_source, appeal_to_authority_score, appeal_to_authority_source, source_citation_score |
| comment_brigade_flags.csv | 4.0 MB | 2026-07-15 | legacy | comment_id, author, score, total_global_comments, brigade_upvote_flag, brigade_downvote_flag |
| commons_authors.csv | 1.9 MB | 2026-06-22 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author |
| commons_llm_results.csv | 0.2 MB | 2026-07-13 | legacy | id, text, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority, procedural_skepticism |
| comparison_askreddit_engagement.csv | 0.0 MB | 2026-07-06 | orphan | primary_move, count, avg_upvotes, avg_controversy |
| comparison_askreddit_scored.parquet | 5.2 MB | 2026-07-06 | legacy (05_Comparison_Exploration.ipynb) |  |
| comparison_askreddit_staged_scored.parquet | 9.1 MB | 2026-07-15 | legacy |  |
| comparison_conspiracy_commons_engagement.csv | 0.0 MB | 2026-07-06 | orphan | primary_move, count, avg_upvotes, avg_controversy |
| comparison_conspiracy_commons_ml_scored.parquet | 3.4 MB | 2026-07-06 | orphan |  |
| comparison_conspiracy_commons_scored.parquet | 1.6 MB | 2026-07-06 | legacy (05_Comparison_Exploration.ipynb) |  |
| comparison_conspiracy_commons_staged_scored.parquet | 2.7 MB | 2026-07-13 | legacy |  |
| comparison_ml_models.pkl | 1.1 MB | 2026-07-06 | legacy |  |
| comparison_politics_scored.parquet | 3.7 MB | 2026-07-15 | legacy |  |
| comparison_politics_staged_scored.parquet | 6.6 MB | 2026-07-15 | legacy |  |
| comparison_topminds_staged_scored.parquet | 9.7 MB | 2026-07-15 | legacy |  |
| comparison_topmindsofreddit_engagement.csv | 0.0 MB | 2026-07-06 | orphan | primary_move, count, avg_upvotes, avg_controversy |
| comparison_topmindsofreddit_scored.parquet | 239.0 MB | 2026-07-06 | legacy (05_Comparison_Exploration.ipynb) |  |
| consensus_stance_queue_strata_map.csv | 0.0 MB | 2026-07-15 | legacy | id, stratum |
| construct_correlation_matrix.csv | 0.0 MB | 2026-07-13 | ACTIVE (master notebook) | , pe_prob, ps_prob, evidence_count, adversarial_count, hedge_count, certainty_count, alt_authority_count |
| corpus_entity_frequency.csv | 193.2 MB | 2026-07-14 | legacy | entity, label, doc_count, in_candidate_list, example_1, example_2, bucket |
| corpus_entity_frequency_cleaned.csv | 140.6 MB | 2026-07-14 | orphan | entity, label, doc_count, in_candidate_list, example_1, bucket |
| corpus_entity_frequency_final.csv | 17.5 MB | 2026-07-14 | legacy | entity, doc_count, in_candidate_list, already_triaged, bucket |
| corpus_metadata.json | 0.0 MB | 2026-06-21 | ACTIVE (master notebook) | raw_comments, usable_comments, threads |
| credibility_signals_v2_PERSONAL_EXP_REVIEW_QUEUE.csv | 0.4 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, upvotes, tagged_span, full_text |
| cross_post_audit_results.csv | 0.2 MB | 2026-06-18 | ACTIVE (master notebook) | source_post_id, external_subreddit, cross_post_score, cross_post_title |
| crosspost_strata_posts_meta.csv | 0.0 MB | 2026-06-21 | ACTIVE (master notebook) | id, post_created_utc, title |
| crosspost_strata_raw_comments.csv | 0.1 MB | 2026-06-21 | ACTIVE (master notebook) | clean_link_id, comment_created_utc, is_insider_num |
| custom_model_classifications_master.csv | 2.9 MB | 2026-06-22 | legacy (Untitled1.ipynb) | id, target_text, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority, procedural_skepticism |
| df.csv | 210.9 MB | 2026-06-22 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | , author, subreddit, comment_count |
| df_rankings_live.csv | 79.8 MB | 2026-06-20 | ACTIVE (master notebook) | author, total_comment_volume, aggregated_text, lexical_score, bin |
| df_users_live.csv | 17.0 MB | 2026-07-17 | ACTIVE (master notebook) | author, total_long_comments, peak_upvotes, median_upvotes, big_hits, aggregated_text |
| dist.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | structural_cohort, sample_size, mean_controversiality, p50_median, p75, p90 |
| domain_epistemic_performance.csv | 0.0 MB | 2026-06-19 | ACTIVE (master notebook) | , domain, citations, avg_upvotes, median_upvotes, avg_controversy, unique_comments |
| domains copy.csv | 0.0 MB | 2026-06-20 | orphan | , domain, citations, avg_upvotes, median_upvotes, avg_controversy, unique_comments |
| domains.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | domain, citations, unique_comments, avg_upvotes, median_upvotes, avg_controversy |
| duckdb_syntactic_candidates.csv | 125.3 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, body, created_utc, id, extracted_span, span_length |
| empath_scores_full.parquet | 2949.3 MB | 2026-07-13 | ACTIVE (master notebook) | id,evidence,adversarial,hedge,certainty,alt_authority,intuitive,pattern |
| empath_scores_full.parquet.bak | 2949.3 MB | 2026-07-18 | orphan |  |
| engagement_regression_results.csv | 0.0 MB | 2026-07-13 | ACTIVE (master notebook) | decile, mean_upvotes, median_upvotes, controversiality_rate, high_traction_rate, min_score, max_score, count |
| ensemble_anti_establishment_stance.csv | 1.5 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_isolated, label_v2_multi, passes_seen, passes_positive, agreement_score |
| ensemble_appeal_to_authority.csv | 1.3 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_lite, label_flash, label_pro, label_v2_multi, passes_seen |
| ensemble_hedged_suspicion.csv | 1.4 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_isolated, label_v2_multi, passes_seen, passes_positive, agreement_score |
| ensemble_insider_ethos.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_lite, label_pro, label_v2_multi, passes_seen, passes_positive |
| ensemble_maverick_authority.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_pass1, label_pass2, label_v2_multi, passes_seen, passes_positive |
| ensemble_personal_experience.csv | 1.3 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_isolated, label_v2_multi, passes_seen, passes_positive, agreement_score |
| ensemble_procedural_skepticism.csv | 1.3 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_lite, label_flash, label_pro, label_v2_multi, passes_seen |
| ensemble_reasonableness_performance.csv | 1.2 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_lite, label_pro, label_v2_multi, passes_seen, passes_positive |
| ensemble_source_citation.csv | 1.3 MB | 2026-07-13 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, upvotes, label_lite, label_flash, label_pro, label_v2_multi, passes_seen |
| entity_context_windows.csv | 7.9 MB | 2026-07-14 | legacy | entity, doc_count, examples |
| entity_disambiguation_classified.csv | 0.8 MB | 2026-07-14 | legacy | cluster, id, classified_as, scores |
| entity_disambiguation_refined.csv | 2.0 MB | 2026-07-14 | legacy | entity, doc_count, in_candidate_list, already_triaged, wp_title, wp_description, match_confident, tier1_bucket_guess |
| entity_final_review.csv | 10.0 MB | 2026-07-14 | ACTIVE (master notebook) | entity, doc_count, best_identity, wp_description, final_bucket_guess, bucket_confidence, disambiguation_note, likely_pure_junk |
| entity_stage_a_filtered.csv | 4.1 MB | 2026-07-14 | legacy | entity, doc_count, in_candidate_list, already_triaged, wp_title, wp_description, match_confident, tier1_bucket_guess |
| entity_unbucketed_with_context.csv | 3.8 MB | 2026-07-14 | legacy | entity, doc_count, in_candidate_list, already_triaged, wp_title, wp_description, match_confident, tier1_bucket_guess |
| entity_wikidata_tier1.csv | 1.4 MB | 2026-07-14 | legacy | entity, doc_count, in_candidate_list, already_triaged, wp_title, wp_description, match_confident, tier1_bucket_guess |
| `factappeal` | 5486.4 MB | 2026-07-18 | ACTIVE (master notebook) |  |
| factappeal_clusters.png | 0.1 MB | 2026-06-16 | legacy (Conspiracy_Pipeline.ipynb) |  |
| false_negative_counts.json | 0.0 MB | 2026-07-02 | ACTIVE (master notebook) | maybe_count |
| filtered_candidates.parquet | 801.3 MB | 2026-07-18 | ACTIVE (master notebook) | id,text,upvotes,controversiality |
| flashpoint_control_threads_2025-01.csv | 0.0 MB | 2026-07-06 | ACTIVE (master notebook) | link_id, comment_count, role |
| full_monthly_new_words.json | 1.6 MB | 2026-06-19 | legacy (ConspiracyMaster_Organized.ipynb) | 2010-08, 2010-09, 2010-10, 2010-11, 2010-12, 2011-01, 2011-02, 2011-03 |
| gc.csv | 0.0 MB | 2026-06-24 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | , 0, 1, 2, 3, 4 |
| gemini_model_comparison_test_v2.json | 0.0 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | case_id, condition, output |
| hedged_suspicion_candidates.csv | 3.6 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, text |
| hedged_suspicion_candidates1.csv | 4.3 MB | 2026-06-23 | orphan | author, text |
| hedged_suspicion_final_hitl_scored.csv | 7.8 MB | 2026-06-23 | legacy (async_llm_scraper.ipynb) | author, text, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority, procedural_skepticism |
| hedged_suspicion_hitl_queue.csv | 2.3 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, author, max_sim_score, n_anchors, n_concealment, pass1_anchor_which, pass2_concealment_which, extracted_span |
| hedged_suspicion_hitl_queue_deduped copy.csv | 0.1 MB | 2026-06-23 | orphan | extracted_span, hitl_label |
| hedged_suspicion_hitl_queue_deduped.csv | 2.3 MB | 2026-06-23 | ACTIVE (master notebook) | id, author, max_sim_score, n_anchors, n_concealment, pass1_anchor_which, pass2_concealment_which, extracted_span |
| hedged_suspicion_ml_predictions.csv | 4.9 MB | 2026-06-24 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, max_sim_score, pass1_anchor_which, extracted_span, body, ml_suspicion_pred, ml_suspicion_prob |
| hedged_suspicion_pass1_only.csv | 4.8 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, max_sim_score, pass1_anchor_which, extracted_span, body |
| hedged_suspicion_pipeline.pkl | 0.2 MB | 2026-06-24 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| hedged_suspicion_tuned_endpoint_classified.csv | 7.5 MB | 2026-06-22 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, text, length, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority |
| hedged_suspicionresults.csv | 1.4 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_isolated, label_v2_multi, passes_seen, passes_positive, agreement_score |
| high_traction_comment_distribution.csv | 0.0 MB | 2026-06-18 | legacy (ConspiracyMaster_mechanical_clean.ipynb) | total_high_traction_comments, thread_count, total_viral_comments_in_bucket, total_mid_high_comments_in_bucket |
| high_upvote_with_topics.parquet | 14.4 MB | 2026-06-17 | ACTIVE (master notebook) | id,text,upvotes,controversiality,topic |
| human_labels_active_learning.csv | 0.0 MB | 2026-06-16 | ACTIVE (master notebook) | id, target_text, upvotes, controversiality, attribution_class, parent_text, human_stance, epistemic_moves |
| insider_ethos_high_probability_candidates copy.csv | 2.0 MB | 2026-06-21 | orphan | id, author, upvotes, controversiality, parent_id, link_id, created_utc, char_length |
| insider_ethos_high_probability_candidates.csv | 10.0 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, author, upvotes, controversiality, parent_id, link_id, created_utc, char_length |
| insider_ethosresults.csv | 1.2 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_lite, label_pro, label_v2_multi, passes_seen, passes_positive |
| insider_matrix.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | insider_segment, total_comments, avg_length, avg_evidence, avg_adversarial, avg_hedge, avg_certainty, avg_pattern |
| insider_presence_threshold_sweep.csv | 0.0 MB | 2026-07-15 | legacy | insider_presence_threshold, n_obs, ols_coef, ols_pvalue, logit_coef, logit_pvalue |
| insider_vote_baselines.csv | 0.0 MB | 2026-06-18 | ACTIVE (master notebook) | month, total_authors, insider_authors, avg_daily_insider_commenters, estimated_daily_insider_votes |
| insiders.csv | 11.1 MB | 2026-06-22 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | , author, total_reddit_comments, conspiracy_comments, conspiracy_ratio, adjacent_comments, network_total, network_ratio |
| institutional_authority_seed_pool.csv | 0.0 MB | 2026-07-15 | legacy | name, domain, basis_type, basis_detail, source_url, tenure_start, tenure_end, in_corpus_window |
| institutional_source_candidates.csv | 0.0 MB | 2026-07-15 | legacy | entity, doc_count, wp_description |
| isolated_anti_establishment_test.json | 0.0 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | case_id, expected, output |
| isolated_hedged_suspicion_test.json | 0.0 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | case_id, expected, output |
| isolated_personal_experience_test.json | 0.0 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | case_id, expected, output |
| jupyter_memory_backup.pkl | 5.2 MB | 2026-06-25 | orphan |  |
| labeled_2k_embedded.parquet | 4.0 MB | 2026-06-22 | legacy (async_llm_scraper.ipynb) | id,embeddings |
| labeled_2k_lr_probs.csv | 1.1 MB | 2026-06-23 | legacy (async_llm_scraper.ipynb) | , text, raw_labels, hedged_suspicion_prob, hedged_suspicion_pred50, hedged_suspicion_pred70, source_citation_prob, source_citation_pred50 |
| labeled_2k_lr_probs.parquet | 4.1 MB | 2026-06-23 | legacy (async_llm_scraper.ipynb) | id,lr_prob |
| labeled_2k_with_scores.csv | 1.1 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | , text, raw_labels, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority |
| labeled_2k_with_scores.parquet | 4.1 MB | 2026-06-23 | legacy (async_llm_scraper.ipynb) | text,raw_labels,anti_establishment_stance,hedged_suspicion,personal_experience,source_cita |
| lexical_baseline_2014-08.csv | 0.1 MB | 2026-07-06 | orphan | word, term_frequency |
| lexical_baseline_2022-08.csv | 0.1 MB | 2026-06-18 | orphan | word, term_frequency |
| lexical_baseline_2023-09.csv | 0.1 MB | 2026-07-06 | orphan | word, term_frequency |
| lexical_baseline_2025-01.csv | 0.1 MB | 2026-06-18 | orphan | word, term_frequency |
| lexical_keyness_2025-01.csv | 0.4 MB | 2026-06-18 | legacy (ConspiracyMaster.ipynb) | word, term_frequency, corpus_prob, askreddit_prob, keyness_ratio |
| lexical_scores_2014-08.csv | 0.1 MB | 2026-07-06 | orphan | author, month_comments, activity_tier, lexical_insider_score |
| lexical_scores_2023-09.csv | 0.3 MB | 2026-07-06 | orphan | author, month_comments, activity_tier, lexical_insider_score |
| lexical_scores_full.parquet | 2946.3 MB | 2026-07-13 | ACTIVE (master notebook) | id,evidence,adversarial,hedge,certainty,alt_authority,intuitive,pattern |
| lexical_scores_sample_2025-01.csv | 0.0 MB | 2026-06-18 | orphan | user_tier, author, num_comments, lexical_insider_score |
| lexical_turnover.csv | 0.0 MB | 2026-06-19 | legacy (ConspiracyMaster_Organized.ipynb) | , month, overlap_with_previous, new_words_count, top_new_words |
| lifecycle_trajectories_local.csv | 56.9 MB | 2026-06-19 | legacy (ConspiracyConcise.ipynb) | author, month_str, months_since_start, alignment_score, total_comments |
| link_type_regression_results.csv | 0.0 MB | 2026-07-15 | legacy | subreddit, model_type, variable, coef, pvalue, se |
| liscc.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | strata, top_commenters_scored, avg_upvotes, avg_lexical_score, median_lexical_score |
| llm_candidate_queue.csv | 70.3 MB | 2026-06-22 | legacy (03_Semantic_Classification.ipynb) | id, text |
| local_model_train_dataset.csv | 0.8 MB | 2026-06-22 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, target_text, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority, procedural_skepticism |
| long_tail.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | total_comments, avg_length, avg_evidence, avg_adversarial, avg_hedge, avg_certainty, avg_alt_authority, avg_intuitive |
| macro_baseline.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | strata, total_threads_measured, total_comments_analyzed, aggregate_regular_ratio_pct |
| mainstream_expert_augmented_superset.csv | 0.1 MB | 2026-07-15 | legacy | name, domain, basis_type, basis_detail, source_url, tenure_start, tenure_end, in_corpus_window |
| mainstream_expert_augmented_superset_temp.csv | 0.4 MB | 2026-07-15 | legacy | name, domain, basis_type, basis_detail, source_url, tenure_start, tenure_end, in_corpus_window |
| mainstream_expert_seed_pool.csv | 0.0 MB | 2026-07-15 | legacy | name, domain, basis_type, basis_detail, source_url, tenure_start, tenure_end, in_corpus_window |
| master_12k_embedded.parquet | 26.4 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id,embeddings |
| master_12k_live_scored.csv | 14.7 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | text, raw_labels, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority, procedural_skepticism |
| master_12k_lr_probs.csv | 15.5 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | text, raw_labels, anti_establishment_stance, hedged_suspicion, personal_experience, source_citation, appeal_to_authority, procedural_skepticism |
| master_thread_synthesis.parquet | 72.3 MB | 2026-06-16 | ACTIVE (master notebook) |  |
| maverick_authority_entities.csv | 0.0 MB | 2026-07-13 | legacy | entity, positive_mentions, negative_mentions, positive_rate, negative_rate, lift |
| maverick_authority_entities_localized.csv | 0.0 MB | 2026-07-13 | ACTIVE (master notebook) | entity, positive_mentions, negative_mentions, positive_rate, negative_rate, lift |
| maverick_authorityresults.csv | 1.2 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_pass1, label_pass2, label_v2_multi, passes_seen, passes_positive |
| maverick_candidate_entities_scored.csv | 0.0 MB | 2026-07-13 | legacy | entity, categories, n_categories, corpus_mentions, decision |
| maverick_entity_mention_candidates.parquet | 14.2 MB | 2026-07-13 | legacy |  |
| maverick_non_person_candidates.csv | 0.0 MB | 2026-07-15 | legacy | entity, wp_description, doc_count, reason_flagged, decision |
| monthTopics1.csv | 0.3 MB | 2026-06-19 | legacy | , Topic, Count, Name, Representation, Representative_Docs |
| `monthly_baselines` | 11.4 MB | 2026-06-21 | legacy |  |
| `monthly_partitions` | 5369.8 MB | 2026-06-21 | legacy (ConspiracyConcise.ipynb) |  |
| monthly_vocabs.pkl | 9.8 MB | 2026-06-19 | legacy (ConspiracyMaster_Organized.ipynb) |  |
| monthly_volume.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | month, n_comments |
| near_duplicate_clusters.parquet | 0.9 MB | 2026-07-18 | ACTIVE (master notebook) | id,cluster_id |
| near_duplicate_clusters_meta.json | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | min_char_length_covered |
| neg_profile.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | total_comments, avg_length, avg_evidence, avg_adversarial, avg_hedge, avg_certainty, avg_alt_authority, avg_intuitive |
| neg_texts.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | upvotes, certainty_count, adversarial_count, text |
| openalex_experts.csv | 0.0 MB | 2026-07-15 | legacy | name, domain, basis_type, basis_detail, source_url, tenure_start, tenure_end, in_corpus_window |
| pairs.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | parent_text, parent_upvotes, child_text, child_upvotes |
| percentiles.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | total_unique_authors, median_comments, p75_comments, p90_comments, p95_comments, p99_comments |
| personal_experienceresults.csv | 1.3 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_isolated, label_v2_multi, passes_seen, passes_positive, agreement_score |
| petscan_experts.csv | 0.4 MB | 2026-07-15 | legacy | name, domain, basis_type, basis_detail, source_url, tenure_start, tenure_end, in_corpus_window |
| pilot.csv | 0.1 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | post_title, parent_text, target_text, upvotes, complexity_score |
| pilot_llm_results_120.csv | 0.2 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | post_title, parent_text, target_text, upvotes, complexity_score, raw_llm_output, intentionality_attribution, rhetorical_stance |
| pos_texts.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | upvotes, pattern_count, evidence_count, text |
| post_title_lookup.csv | 268.3 MB | 2026-07-18 | ACTIVE (master notebook) | url, reddit_title |
| probabilities_hedged_suspicion.json | 0.1 MB | 2026-06-22 | legacy (async_llm_scraper.ipynb) | 0, 1, 2, 3, 4, 5, 6, 7 |
| probabilities_source_citation.json | 0.1 MB | 2026-06-22 | legacy (async_llm_scraper.ipynb) | 0, 1, 2, 3, 4, 5, 6, 7 |
| procedural_skepticismresults.csv | 1.3 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_lite, label_flash, label_pro, label_v2_multi, passes_seen |
| pubmeds.csv | 0.1 MB | 2026-06-20 | orphan | , pubmed_id, n |
| pure_population_regression_results.csv | 0.0 MB | 2026-07-15 | legacy | population, model, construct, coef, se, pvalue, n_obs |
| raw_files_trace_summary.csv | 0.0 MB | 2026-07-20 | orphan | file, size_mb, row_count, min_utc, max_utc, error |
| reasonableness_performanceresults.csv | 1.2 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_lite, label_pro, label_v2_multi, passes_seen, passes_positive |
| refined_regression_results.csv | 0.0 MB | 2026-07-15 | legacy | subreddit, variable, coef, se, pvalue, n_obs |
| refined_regression_results_v2.csv | 0.0 MB | 2026-07-20 | legacy | subreddit, variable, coef, se, pvalue, n_obs |
| refined_semantic_keyness_results.csv | 0.6 MB | 2026-07-15 | legacy | word, freq_c1, freq_c2, pct_c1, pct_c2, log_likelihood, comparison, subreddit |
| refined_semantic_keyness_results_v2.csv | 6.6 MB | 2026-07-15 | legacy | word, freq_c1, freq_c2, pct_c1, pct_c2, log_likelihood, comparison, subreddit |
| research_corpus_enriched.parquet | 1637.7 MB | 2026-07-18 | ACTIVE (master notebook) | id,text,upvotes,controversiality,author,created_utc |
| research_corpus_staged_scores.parquet | 53.0 MB | 2026-07-13 | legacy | id,pe_prob,ps_prob,sc_prob,hs_prob,ma_prob |
| research_corpus_staged_scores_full21m.parquet | 206.1 MB | 2026-07-13 | legacy | id,pe_prob,ps_prob,sc_prob,hs_prob,ma_prob |
| research_corpus_staged_scores_full21m.parquet.bak | 206.1 MB | 2026-07-18 | orphan |  |
| sample_2k_id_map.csv | 0.0 MB | 2026-07-06 | legacy | row_idx, reddit_id |
| sample_validation_results.csv | 0.1 MB | 2026-06-24 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id, max_sim_score, pass1_anchor_which, extracted_span, body, gemini_prediction |
| sampled_strata_posts_meta.csv | 0.0 MB | 2026-06-21 | ACTIVE (master notebook) | id, post_created_utc, title |
| sampled_strata_raw_comments.csv | 0.1 MB | 2026-06-21 | ACTIVE (master notebook) | clean_link_id, comment_created_utc, is_insider_num |
| semantic_keyness_results.csv | 0.5 MB | 2026-07-15 | legacy | word, freq_maverick, freq_expert, pct_maverick, pct_expert, log_likelihood, subreddit |
| semantic_sample_500k.parquet | 31.1 MB | 2026-06-16 | legacy (ConspiracyMaster.ipynb) | id,text |
| semantic_sample_500k_EMBEDDED.parquet | 187.4 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | id,embeddings |
| semantic_scores_sample.parquet | 37.9 MB | 2026-06-16 | legacy (ConspiracyMaster.ipynb) | id,score |
| source_authority_scores.csv | 0.0 MB | 2026-07-20 | legacy | entity, doc_count, category, matched_name, dataset, reliability_label, rank_or_score, bias_label |
| source_citationresults.csv | 1.3 MB | 2026-07-13 | orphan | id, target_text, upvotes, label_lite, label_flash, label_pro, label_v2_multi, passes_seen |
| spacy_attributed_comments.parquet | 266.9 MB | 2026-06-16 | ACTIVE (master notebook) | id,text,attribution_class |
| spacy_audit_scratchpad.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | attribution_class, text |
| stage_b_credential_pattern_hits.csv | 1.0 MB | 2026-07-14 | legacy | name, trigger, context, id |
| stage_b_credential_pattern_hits_cleaned.csv | 0.8 MB | 2026-07-14 | orphan | name, trigger, context, id, name_clean |
| stage_b_word_bags.json | 5.8 MB | 2026-07-14 | legacy | bill, hunter, kennedy, clinton, sanders, rich, tucker |
| stage_c_signature_words.json | 0.0 MB | 2026-07-14 | legacy | bill, hunter, kennedy, clinton, sanders |
| stage_d_new_candidates.csv | 0.0 MB | 2026-07-14 | orphan | entity, doc_count, in_candidate_list, already_triaged |
| stage_d_resolved.csv | 0.0 MB | 2026-07-14 | legacy | entity, doc_count, in_candidate_list, already_triaged, wp_title, wp_description, match_confident, tier1_bucket_guess |
| stage_e_category_buckets.csv | 7.4 MB | 2026-07-14 | legacy | entity, doc_count, wp_title, wp_description, tier1_bucket_guess, category_bucket_guess, substantive_categories_str, category_bucket_n_matches |
| stage_f_bottom_up_clusters.csv | 0.4 MB | 2026-07-14 | legacy | entity, doc_count, best_identity, natural_cluster |
| stage_g_classified.csv | 2.0 MB | 2026-07-14 | legacy | cluster, classified_as |
| stage_g_cluster_summary.csv | 0.0 MB | 2026-07-14 | legacy | cluster, n_candidates, candidates, n_bare_instances, n_resolved, resolution_rate, disambiguation_note |
| stage_g_signature_words.json | 0.1 MB | 2026-07-14 | legacy | Donald, John, Jones, Barr, Steele, Paul, Cheney, Harris |
| stage_g_word_bags.json | 64.9 MB | 2026-07-14 | legacy | Donald, John, Jones, Barr, Steele, Paul, Cheney, Harris |
| staged_pipeline_models.joblib | 0.2 MB | 2026-07-13 | legacy |  |
| stance_detection_prototype_results.csv | 0.0 MB | 2026-07-15 | orphan | dimension, value, count, agreement_rate, disagreement_rate, neutral_rate |
| synthesis_interaction_results.csv | 0.0 MB | 2026-07-14 | legacy | term, coef, se, pvalue, tstat, n_obs, r2 |
| synthesis_regression_results.csv | 0.0 MB | 2026-07-14 | legacy | elasticity_strata, insider_threshold, model_name, n_obs, r2_or_pseudo_r2, model_sig_pvalue, pe_prob_coef, pe_prob_se |
| synthesis_regression_results_filtered.csv | 0.0 MB | 2026-07-14 | legacy | elasticity_strata, insider_threshold, model_name, n_obs, r2_or_pseudo_r2, model_sig_pvalue, pe_prob_coef, pe_prob_se |
| target_posts_meta.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | id, post_created_utc, title |
| thread.csv | 0.0 MB | 2026-06-20 | orphan | , clean_link_id, comment_created_utc, is_insider_num, hours_since_post, rolling_insider_ratio |
| thread_demographic_raw_comments.csv | 0.3 MB | 2026-06-21 | ACTIVE (master notebook) | clean_link_id, author, score, comment_created_utc, user_type |
| thread_demographic_timelines.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | clean_link_id, hour_since_post, total_comments_in_hour, regular_user_comments, outsider_comments, native_regular_ratio_pct |
| thread_insider_presence.csv | 27.3 MB | 2026-07-14 | legacy | post_id, n_distinct_commenters, n_insider_commenters, insider_presence_ratio |
| thread_quality_metrics.csv | 84.2 MB | 2026-07-15 | legacy | post_id, post_score, num_comments, num_crossposts, created_utc, subreddit, is_high_crosspost, elasticity_ratio |
| thread_quality_metrics.csv.bak_17k | 0.8 MB | 2026-07-15 | orphan |  |
| threads_insider_filtered.parquet | 2.2 MB | 2026-07-03 | legacy | link_id |
| tier2_scored_candidates.csv | 122.5 MB | 2026-06-23 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | author, body, created_utc, id, extracted_span, span_length, word_count, max_sim_score |
| tiers.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | activity_tier, number_of_authors, total_comments_generated, pct_of_authors, pct_of_total_comments |
| tightened_prompt_test.json | 0.0 MB | 2026-06-21 | legacy (ConspiracyMaster_Final_Architecture copy.ipynb) | case_id, output |
| top_30_per_category.csv | 1.3 MB | 2026-06-17 | ACTIVE (master notebook) | category, id, author, upvotes, controversiality, char_length, word_count, density_score |
| top_alt_media_articles.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | domain, url, citations, avg_upvotes, title |
| top_mainstream_articles.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | domain, url, citations, avg_upvotes, title |
| top_pubmed_studies.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | pubmed_id, title, authors, reference_count, url |
| top_wikileaks_documents.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | domain, url, citations, avg_upvotes, title |
| top_wikipedia_canon.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | wiki_slug, title, reference_count, url |
| top_youtube_videos.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | video_id, title, channel, citations, url |
| topic_epistemic_profiles.csv | 0.0 MB | 2026-06-19 | legacy (ConspiracyMaster_Organized.ipynb) | , topic_name, total_comments, avg_evidence, avg_quantitative, avg_anecdotal, avg_demand, avg_meta |
| topic_temporal_dominance.csv | 0.0 MB | 2026-07-20 | legacy | year_month, assigned_topic, topic_name, super_topic, dominant_topic_count, total_monthly_comments, dominant_topic_share |
| topic_time_regression_results.csv | 0.0 MB | 2026-07-20 | legacy | stratum, model_type, variable, coef, se, pvalue, n_obs, note |
| unfiltered_mid_high_thread_ids.parquet | 0.8 MB | 2026-06-18 | ACTIVE (master notebook) | link_id |
| unfiltered_viral_thread_ids.parquet | 0.5 MB | 2026-06-18 | ACTIVE (master notebook) | link_id |
| upvote_tier_counts.csv | 0.0 MB | 2026-07-18 | ACTIVE (master notebook) | upvote_tier, n |
| url_level_citations.csv | 0.3 MB | 2026-07-18 | ACTIVE (master notebook) | domain, url, citations, avg_upvotes |
| us_health_office_rosters.csv | 0.0 MB | 2026-07-15 | legacy | name, domain, basis_type, basis_detail, source_url, tenure_start, tenure_end, in_corpus_window |
| user_topic_specialization.csv | 5.0 MB | 2026-07-20 | legacy | author, total_assigned_comments, hhi_specialization, dominant_topic_id, dominant_topic_fraction, dominant_topic_name, dominant_super_topic, total_long_comments |
| validation_spot_checks.csv | 0.1 MB | 2026-07-02 | ACTIVE (master notebook) | dimension, type, score, upvotes, text |
| wikipedia.csv | 3.8 MB | 2026-06-20 | orphan | , wiki_slug, n |

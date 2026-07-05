# data/processed Manifest

Generated 2026-07-06 by cross-referencing every file against the master notebook,
archived notebooks, and all Python modules. Statuses:
- **ACTIVE** — read or written by `ConspiracyMaster_Refactored.ipynb`
- **legacy** — referenced only by archived/legacy notebooks (kept for provenance)
- **orphan** — referenced by nothing that survives; verify then delete or rename

Known decodings: `attp.csv` = all-time top posts. `jupyter_memory_backup.pkl` is a
truncated/corrupt session dump (unreadable — safe to delete).

| File | Size | Modified | Status | Columns (first 8) |
|---|---|---|---|---|
| api_audit_sampling_1k.parquet | 0.0 MB | 2026-06-18 | ACTIVE (master notebook) | link_id,true_high_traction_count,strata |
| attp.csv | 0.1 MB | 2026-06-21 | ACTIVE (master notebook) | title,domain,score,num_comments,upvote_ratio |
| attributed.csv | 262.4 MB | 2026-06-20 | ACTIVE (master notebook) | text,upvotes,controversiality,attribution_class |
| bertopic_model | 761.5 MB | 2026-06-17 | ACTIVE (master notebook) |  |
| breakouts.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | title,score,num_comments,num_crossposts,upvote_ratio,permalink |
| brigade_test.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | upvote_tier,total_comments,avg_controversiality,expertise_talk_percentage |
| corpus_metadata.json | 0.0 MB | 2026-06-21 | ACTIVE (master notebook) |  |
| cross_post_audit_results.csv | 0.2 MB | 2026-06-18 | ACTIVE (master notebook) | source_post_id,external_subreddit,cross_post_score,cross_post_title |
| crosspost_strata_posts_meta.csv | 0.0 MB | 2026-06-21 | ACTIVE (master notebook) | id,post_created_utc,title |
| crosspost_strata_raw_comments.csv | 0.1 MB | 2026-06-21 | ACTIVE (master notebook) | clean_link_id,comment_created_utc,is_insider_num |
| df_rankings_live.csv | 83.7 MB | 2026-06-20 | ACTIVE (master notebook) | author,total_comment_volume,aggregated_text,lexical_score,bin |
| df_users_live.csv | 23.4 MB | 2026-06-20 | ACTIVE (master notebook) | author,peak_upvotes,num_long_comments,aggregated_text,lexical_insider_score |
| dist.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | structural_cohort,sample_size,mean_controversiality,p50_median,p75,p90 |
| domain_epistemic_performance.csv | 0.0 MB | 2026-06-19 | ACTIVE (master notebook) | Unnamed: 0,domain,citations,avg_upvotes,median_upvotes,avg_controversy,unique_comments |
| domains.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | domain,citations,unique_comments,avg_upvotes,median_upvotes,avg_controversy |
| empath_scores_full.parquet | 3092.6 MB | 2026-06-17 | ACTIVE (master notebook) |  |
| factappeal | 5752.6 MB | 2026-07-02 | ACTIVE (master notebook) |  |
| false_negative_counts.json | 0.0 MB | 2026-07-02 | ACTIVE (master notebook) |  |
| filtered_candidates.parquet | 840.2 MB | 2026-07-02 | ACTIVE (master notebook) |  |
| hedged_suspicion_hitl_queue_deduped.csv | 2.4 MB | 2026-06-23 | ACTIVE (master notebook) | id,author,max_sim_score,n_anchors,n_concealment,pass1_anchor_which,pass2_concealment_which |
| high_upvote_with_topics.parquet | 15.1 MB | 2026-06-17 | ACTIVE (master notebook) | id,text,upvotes,controversiality,evidence_count,adversarial_count,hedge_count,certainty_co |
| human_labels_active_learning.csv | 0.0 MB | 2026-06-16 | ACTIVE (master notebook) | id,target_text,upvotes,controversiality,attribution_class,parent_text,human_stance,epistem |
| insider_matrix.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | insider_segment,total_comments,avg_length,avg_evidence,avg_adversarial,avg_hedge,avg_certa |
| insider_vote_baselines.csv | 0.0 MB | 2026-06-18 | ACTIVE (master notebook) | month,total_authors,insider_authors,avg_daily_insider_commenters,estimated_daily_insider_v |
| lexical_scores_full.parquet | 3089.4 MB | 2026-06-16 | ACTIVE (master notebook) |  |
| liscc.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | strata,top_commenters_scored,avg_upvotes,avg_lexical_score,median_lexical_score |
| long_tail.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | total_comments,avg_length,avg_evidence,avg_adversarial,avg_hedge,avg_certainty,avg_alt_aut |
| macro_baseline.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | strata,total_threads_measured,total_comments_analyzed,aggregate_regular_ratio_pct |
| master_thread_synthesis.parquet | 75.8 MB | 2026-06-16 | ACTIVE (master notebook) |  |
| neg_profile.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | total_comments,avg_length,avg_evidence,avg_adversarial,avg_hedge,avg_certainty,avg_alt_aut |
| neg_texts.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | upvotes,certainty_count,adversarial_count,text |
| pairs.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | parent_text,parent_upvotes,child_text,child_upvotes |
| percentiles.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | total_unique_authors,median_comments,p75_comments,p90_comments,p95_comments,p99_comments |
| pos_texts.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | upvotes,pattern_count,evidence_count,text |
| research_corpus_enriched.parquet | 1717.3 MB | 2026-07-02 | ACTIVE (master notebook) |  |
| sampled_strata_posts_meta.csv | 0.0 MB | 2026-06-21 | ACTIVE (master notebook) | id,post_created_utc,title |
| sampled_strata_raw_comments.csv | 0.1 MB | 2026-06-21 | ACTIVE (master notebook) | clean_link_id,comment_created_utc,is_insider_num |
| spacy_attributed_comments.parquet | 279.9 MB | 2026-06-16 | ACTIVE (master notebook) |  |
| spacy_audit_scratchpad.csv | 0.1 MB | 2026-07-02 | ACTIVE (master notebook) | attribution_class,text |
| target_posts_meta.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | id,post_created_utc,title |
| thread_demographic_raw_comments.csv | 0.3 MB | 2026-06-21 | ACTIVE (master notebook) | clean_link_id,author,score,comment_created_utc,user_type |
| thread_demographic_timelines.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | clean_link_id,hour_since_post,total_comments_in_hour,regular_user_comments,outsider_commen |
| tiers.csv | 0.0 MB | 2026-06-20 | ACTIVE (master notebook) | activity_tier,number_of_authors,total_comments_generated,pct_of_authors,pct_of_total_comme |
| top_30_per_category.csv | 1.4 MB | 2026-06-17 | ACTIVE (master notebook) | category,id,author,upvotes,controversiality,char_length,word_count,density_score |
| unfiltered_mid_high_thread_ids.parquet | 0.9 MB | 2026-06-18 | ACTIVE (master notebook) | link_id |
| unfiltered_viral_thread_ids.parquet | 0.5 MB | 2026-06-18 | ACTIVE (master notebook) | link_id |
| validation_spot_checks.csv | 0.1 MB | 2026-07-02 | ACTIVE (master notebook) | dimension,type,score,upvotes,text |
| exports | 9.4 MB | 2026-06-19 | legacy (notebooks/archive/ConspiracyConcise.ipynb) |  |
| lifecycle_trajectories_local.csv | 59.7 MB | 2026-06-19 | legacy (notebooks/archive/ConspiracyConcise.ipynb) | author,month_str,months_since_start,alignment_score,total_comments |
| monthly_partitions | 5630.6 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyConcise.ipynb) |  |
| top_pubmed_studies.csv | 0.0 MB | 2026-06-16 | legacy (notebooks/archive/ConspiracyFindings.ipynb) | pm_id,reference_count |
| top_wikipedia_canon.csv | 0.0 MB | 2026-06-16 | legacy (notebooks/archive/ConspiracyFindings.ipynb) | wiki_slug,reference_count |
| top_youtube_videos.csv | 0.0 MB | 2026-06-16 | legacy (notebooks/archive/ConspiracyFindings.ipynb) | video_id,reference_count |
| appeal_to_authority_candidates.csv | 6.3 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,text,hitl_label |
| appeal_to_authority_tuned_endpoint_classified.csv | 6.3 MB | 2026-06-22 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,target_text,anti_establishment_stance,hedged_suspicion,personal_experience,source_c |
| author_crawl_queue.csv | 13.1 MB | 2026-06-22 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,r_conspiracy_comments |
| author_subreddit_footprints.csv | 6.8 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,subreddit,comment_count |
| author_subreddit_footprints_async.csv | 205.5 MB | 2026-06-22 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,subreddit,comment_count |
| candidates_10k_embedded.parquet | 24.2 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,text,anti_establishment_stance,hedged_suspicion,personal_experience,source_citation |
| clean.csv | 126.5 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,body,created_utc,id,extracted_span,span_length,word_count |
| commons_authors.csv | 1.9 MB | 2026-06-22 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author |
| credibility_signals_v2_PERSONAL_EXP_REVIEW_QUEUE.csv | 0.5 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | id,upvotes,tagged_span,full_text |
| df.csv | 221.2 MB | 2026-06-22 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | Unnamed: 0,author,subreddit,comment_count |
| duckdb_syntactic_candidates.csv | 131.3 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,body,created_utc,id,extracted_span,span_length |
| full_corpus_suspicion_scores.parquet | 488.8 MB | 2026-06-24 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| gc.csv | 0.0 MB | 2026-06-24 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | Unnamed: 0,0,1,2,3,4 |
| gemini_model_comparison_test_v2.json | 0.0 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| hedged_suspicion_candidates.csv | 3.8 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,text |
| hedged_suspicion_hitl_queue.csv | 2.4 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | id,author,max_sim_score,n_anchors,n_concealment,pass1_anchor_which,pass2_concealment_which |
| hedged_suspicion_ml_predictions.csv | 5.1 MB | 2026-06-24 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | id,max_sim_score,pass1_anchor_which,extracted_span,body,ml_suspicion_pred,ml_suspicion_pro |
| hedged_suspicion_pass1_only.csv | 5.1 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | id,max_sim_score,pass1_anchor_which,extracted_span,body |
| hedged_suspicion_pipeline.pkl | 0.2 MB | 2026-06-24 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| hedged_suspicion_tuned_endpoint_classified.csv | 7.9 MB | 2026-06-22 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,text,length,anti_establishment_stance,hedged_suspicion,personal_experience,source_c |
| insider_ethos_high_probability_candidates.csv | 10.5 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | id,author,upvotes,controversiality,parent_id,link_id,created_utc,char_length |
| insiders.csv | 11.7 MB | 2026-06-22 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | Unnamed: 0,author,total_reddit_comments,conspiracy_comments,conspiracy_ratio,adjacent_comm |
| isolated_anti_establishment_test.json | 0.0 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| isolated_hedged_suspicion_test.json | 0.0 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| isolated_personal_experience_test.json | 0.0 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| labeled_2k_with_scores.csv | 1.1 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | Unnamed: 0,text,raw_labels,anti_establishment_stance,hedged_suspicion,personal_experience, |
| local_model_train_dataset.csv | 0.8 MB | 2026-06-22 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | id,target_text,anti_establishment_stance,hedged_suspicion,personal_experience,source_citat |
| master_12k_embedded.parquet | 27.7 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | text,raw_labels,anti_establishment_stance,hedged_suspicion,personal_experience,source_cita |
| master_12k_live_scored.csv | 15.4 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | text,raw_labels,anti_establishment_stance,hedged_suspicion,personal_experience,source_cita |
| master_12k_lr_probs.csv | 16.3 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | text,raw_labels,anti_establishment_stance,hedged_suspicion,personal_experience,source_cita |
| pilot.csv | 0.2 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | post_title,parent_text,target_text,upvotes,complexity_score |
| pilot_llm_results_120.csv | 0.2 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | post_title,parent_text,target_text,upvotes,complexity_score,raw_llm_output,intentionality_ |
| sample_validation_results.csv | 0.1 MB | 2026-06-24 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | id,max_sim_score,pass1_anchor_which,extracted_span,body,gemini_prediction |
| semantic_sample_500k.parquet | 32.7 MB | 2026-06-16 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | id,author,upvotes,controversiality,parent_id,link_id,created_utc,char_length |
| semantic_sample_500k_EMBEDDED.parquet | 196.5 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| tier2_scored_candidates.csv | 128.5 MB | 2026-06-23 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) | author,body,created_utc,id,extracted_span,span_length,word_count,max_sim_score |
| tightened_prompt_test.json | 0.0 MB | 2026-06-21 | legacy (notebooks/archive/ConspiracyMaster_Final_Architecture copy.ipynb) |  |
| full_monthly_new_words.json | 1.7 MB | 2026-06-19 | legacy (notebooks/archive/ConspiracyMaster_Organized.ipynb) |  |
| lexical_turnover.csv | 0.0 MB | 2026-06-19 | legacy (notebooks/archive/ConspiracyMaster_Organized.ipynb) | Unnamed: 0,month,overlap_with_previous,new_words_count,top_new_words |
| monthly_vocabs.pkl | 10.3 MB | 2026-06-19 | legacy (notebooks/archive/ConspiracyMaster_Organized.ipynb) |  |
| topic_epistemic_profiles.csv | 0.0 MB | 2026-06-19 | legacy (notebooks/archive/ConspiracyMaster_Organized.ipynb) | Unnamed: 0,topic_name,total_comments,avg_evidence,avg_quantitative,avg_anecdotal,avg_deman |
| census_ordered_targets.parquet | 1.5 MB | 2026-06-18 | legacy (notebooks/archive/ConspiracyMaster_mechanical_clean.ipynb) | link_id,traction_density |
| high_traction_comment_distribution.csv | 0.0 MB | 2026-06-18 | legacy (notebooks/archive/ConspiracyMaster_mechanical_clean.ipynb) | total_high_traction_comments,thread_count,total_viral_comments_in_bucket,total_mid_high_co |
| factappeal_clusters.png | 0.1 MB | 2026-06-16 | legacy (notebooks/legacy_production/Conspiracy_Pipeline.ipynb) |  |
| semantic_scores_sample.parquet | 39.8 MB | 2026-06-16 | legacy (notebooks/legacy_production/Conspiracy_Pipeline.ipynb) | id,author,upvotes,controversiality,parent_id,link_id,created_utc,char_length |
| cascade_final_classifications.csv | 1.8 MB | 2026-06-22 | legacy (notebooks/pipeline/03_Semantic_Classification.ipynb) | id,target_text,anti_establishment_stance,hedged_suspicion,personal_experience,source_citat |
| llm_candidate_queue.csv | 73.7 MB | 2026-06-22 | legacy (notebooks/pipeline/03_Semantic_Classification.ipynb) | id,text |
| custom_model_classifications_master.csv | 3.0 MB | 2026-06-22 | legacy (notebooks/scratchpads/Untitled1.ipynb) | id,target_text,anti_establishment_stance,hedged_suspicion,personal_experience,source_citat |
| combined_human_scores.csv | 0.1 MB | 2026-06-23 | legacy (notebooks/scratchpads/async_llm_scraper.ipynb) | row_idx,hedged_suspicion_score,hedged_suspicion_source,anti_establishment_stance_score,ant |
| labeled_2k_embedded.parquet | 4.2 MB | 2026-06-22 | legacy (notebooks/scratchpads/async_llm_scraper.ipynb) | text,raw_labels,anti_establishment_stance,hedged_suspicion,personal_experience,source_cita |
| labeled_2k_lr_probs.csv | 1.2 MB | 2026-06-23 | legacy (notebooks/scratchpads/async_llm_scraper.ipynb) | Unnamed: 0,text,raw_labels,hedged_suspicion_prob,hedged_suspicion_pred50,hedged_suspicion_ |
| labeled_2k_lr_probs.parquet | 4.3 MB | 2026-06-23 | legacy (notebooks/scratchpads/async_llm_scraper.ipynb) | text,raw_labels,anti_establishment_stance,hedged_suspicion,personal_experience,source_cita |
| labeled_2k_with_scores.parquet | 4.3 MB | 2026-06-23 | legacy (notebooks/scratchpads/async_llm_scraper.ipynb) | text,raw_labels,anti_establishment_stance,hedged_suspicion,personal_experience,source_cita |
| probabilities_hedged_suspicion.json | 0.1 MB | 2026-06-22 | legacy (notebooks/scratchpads/async_llm_scraper.ipynb) |  |
| probabilities_source_citation.json | 0.1 MB | 2026-06-22 | legacy (notebooks/scratchpads/async_llm_scraper.ipynb) |  |
| MUdetails.csv | 0.0 MB | 2026-06-21 | orphan | link_id,post_title,post_url,comment_text,comment_score |
| STRATIFIED_SAMPLE_appeal_to_authority.csv | 0.0 MB | 2026-06-22 | orphan | id,category,upvotes,human_verdict,notes,tagged_spans,full_text |
| STRATIFIED_SAMPLE_procedural_skepticism.csv | 0.0 MB | 2026-06-22 | orphan | id,category,upvotes,human_verdict,notes,tagged_spans,full_text |
| STRATIFIED_SAMPLE_source_citation.csv | 0.0 MB | 2026-06-22 | orphan | id,category,upvotes,human_verdict,notes,tagged_spans,full_text |
| anti_establishment_stanceresults.csv | 1.1 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_isolated,label_v2_multi,passes_seen,passes_positive,agreement |
| appeal_to_authorityresults.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_flash,label_pro,label_v2_multi,passes_seen |
| attributions.csv | 0.0 MB | 2026-06-20 | orphan | Unnamed: 0,attribution_class,n,pct |
| cascade_anti_establishment_stance.csv | 1.1 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| cascade_appeal_to_authority.csv | 0.9 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| cascade_hedged_suspicion.csv | 1.0 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| cascade_insider_ethos.csv | 0.8 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| cascade_maverick_authority.csv | 0.9 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| cascade_personal_experience.csv | 0.9 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| cascade_procedural_skepticism.csv | 0.9 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| cascade_reasonableness_performance.csv | 0.8 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| cascade_source_citation.csv | 0.9 MB | 2026-06-21 | orphan | id,upvotes,target_text,pass1_lite,pass2_flash,pass3_pro,cascade_outcome,final_spans |
| domains copy.csv | 0.0 MB | 2026-06-20 | orphan | Unnamed: 0,domain,citations,avg_upvotes,median_upvotes,avg_controversy,unique_comments |
| ensemble_anti_establishment_stance.csv | 1.1 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_isolated,label_v2_multi,passes_seen,passes_positive,agreement |
| ensemble_appeal_to_authority.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_flash,label_pro,label_v2_multi,passes_seen |
| ensemble_hedged_suspicion.csv | 1.0 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_isolated,label_v2_multi,passes_seen,passes_positive,agreement |
| ensemble_insider_ethos.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_pro,label_v2_multi,passes_seen,passes_positive |
| ensemble_maverick_authority.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_pass1,label_pass2,label_v2_multi,passes_seen,passes_positive |
| ensemble_personal_experience.csv | 1.0 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_isolated,label_v2_multi,passes_seen,passes_positive,agreement |
| ensemble_procedural_skepticism.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_flash,label_pro,label_v2_multi,passes_seen |
| ensemble_reasonableness_performance.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_pro,label_v2_multi,passes_seen,passes_positive |
| ensemble_source_citation.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_flash,label_pro,label_v2_multi,passes_seen |
| filtered.csv | 3123.4 MB | 2026-07-02 | orphan | id,author,text |
| flashpoint_control_threads_2025-01.csv | 0.0 MB | 2026-07-06 | orphan | link_id,comment_count,role |
| hedged_suspicion_candidates1.csv | 4.5 MB | 2026-06-23 | orphan | author,text |
| hedged_suspicion_final_hitl_scored.csv | 8.2 MB | 2026-06-23 | orphan | author,text,anti_establishment_stance,hedged_suspicion,personal_experience,source_citation |
| hedged_suspicion_hitl_queue_deduped copy.csv | 0.1 MB | 2026-06-23 | orphan | extracted_span,hitl_label |
| hedged_suspicionresults.csv | 1.0 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_isolated,label_v2_multi,passes_seen,passes_positive,agreement |
| insider_ethos_high_probability_candidates copy.csv | 2.1 MB | 2026-06-21 | orphan | id,author,upvotes,controversiality,parent_id,link_id,created_utc,char_length |
| insider_ethosresults.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_pro,label_v2_multi,passes_seen,passes_positive |
| jupyter_memory_backup.pkl | 5.4 MB | 2026-06-25 | orphan |  |
| lexical_baseline_2022-08.csv | 0.1 MB | 2026-06-18 | orphan | word,term_frequency |
| lexical_baseline_2025-01.csv | 0.1 MB | 2026-06-18 | orphan | word,term_frequency |
| lexical_keyness_2025-01.csv | 0.4 MB | 2026-06-18 | orphan | word,term_frequency,corpus_prob,askreddit_prob,keyness_ratio |
| lexical_scores_sample_2025-01.csv | 0.0 MB | 2026-06-18 | orphan | user_tier,author,num_comments,lexical_insider_score |
| maverick_authorityresults.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_pass1,label_pass2,label_v2_multi,passes_seen,passes_positive |
| monthTopics1.csv | 0.3 MB | 2026-06-19 | orphan | Unnamed: 0,Topic,Count,Name,Representation,Representative_Docs |
| monthly_baselines | 11.9 MB | 2026-06-21 | orphan |  |
| personal_experienceresults.csv | 1.0 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_isolated,label_v2_multi,passes_seen,passes_positive,agreement |
| procedural_skepticismresults.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_flash,label_pro,label_v2_multi,passes_seen |
| pubmeds.csv | 0.1 MB | 2026-06-20 | orphan | Unnamed: 0,pubmed_id,n |
| reasonableness_performanceresults.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_pro,label_v2_multi,passes_seen,passes_positive |
| source_citationresults.csv | 0.9 MB | 2026-06-21 | orphan | id,target_text,upvotes,label_lite,label_flash,label_pro,label_v2_multi,passes_seen |
| thread.csv | 0.1 MB | 2026-06-20 | orphan | Unnamed: 0,clean_link_id,comment_created_utc,is_insider_num,hours_since_post,rolling_insid |
| threads_insider_filtered.parquet | 2.3 MB | 2026-07-03 | orphan | post_id,created_utc,title,domain,url,post_score,total_comments,avg_comment_upvotes |
| wikipedia.csv | 3.9 MB | 2026-06-20 | orphan | Unnamed: 0,wiki_slug,n |
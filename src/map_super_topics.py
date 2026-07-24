import os
import pandas as pd

def main():
    print("--- Step 4: Re-deriving and Mapping Cohesive Super-Topic Groups (PRECISE & LOGICAL) ---")
    
    mapping_path = 'data/processed/topic_super_topic_mapping.csv'
    
    # Core mappings of the newly discovered topics to the 6 Super-Topics
    # Only topics that are a clear, semantic, and high-precision fit are mapped.
    # Everything else defaults to "Other / General Conspiracy", preserving taxonomic integrity.
    
    super_topic_assignments = {
        # 1. Geopolitics, Wars & Whistleblowers
        6: "Geopolitics, Wars & Whistleblowers",   # russia_ukraine_russian_putin
        7: "Geopolitics, Wars & Whistleblowers",   # israel_jews_jewish_israeli
        12: "Geopolitics, Wars & Whistleblowers",  # fbi_cia_mueller_assange (Assange, WikiLeaks)
        25: "Geopolitics, Wars & Whistleblowers",  # china_chinese_taiwan_tariffs
        31: "Geopolitics, Wars & Whistleblowers",  # isis_syria_al_islam
        56: "Geopolitics, Wars & Whistleblowers",  # america_uk_country_american
        75: "Geopolitics, Wars & Whistleblowers",  # war_wars_ww3_america
        76: "Geopolitics, Wars & Whistleblowers",  # flag_false_flags_attack
        77: "Geopolitics, Wars & Whistleblowers",  # msm_news_fox_propaganda
        79: "Geopolitics, Wars & Whistleblowers",  # nuclear_nukes_nuke_weapons
        81: "Geopolitics, Wars & Whistleblowers",  # jfk_kennedy_oswald_assassination (JFK, CIA)
        82: "Geopolitics, Wars & Whistleblowers",  # propaganda_campaign_conditioned_government
        
        # 2. 9/11 & Structural Collapses
        10: "9/11 & Structural Collapses",         # building_plane_collapse_towers
        70: "9/11 & Structural Collapses",         # 11_911_inside_bush
        
        # 3. Elections, Finance & Control
        1: "Elections, Finance & Control",          # money_tax_taxes_pay
        5: "Elections, Finance & Control",          # kamala_hillary_tulsi_pelosi
        13: "Elections, Finance & Control",         # election_fraud_vote_ballots
        18: "Elections, Finance & Control",         # biden_trump_joe_president
        27: "Elections, Finance & Control",         # capitalism_communism_socialism_socialist
        50: "Elections, Finance & Control",         # trump_president_establishment_people
        59: "Elections, Finance & Control",         # party_republicans_democrats_republican
        73: "Elections, Finance & Control",         # healthcare_insurance_obamacare_health
        84: "Elections, Finance & Control",         # obama_bush_president_bushes
        90: "Elections, Finance & Control",         # sub_politics_trump_comments
        95: "Elections, Finance & Control",         # oil_gas_prices_price
        
        # 4. Alex Jones & Deep State/Secret Societies
        22: "Alex Jones & Deep State/Secret Societies",  # epstein_trump_maxwell_jeffrey
        39: "Alex Jones & Deep State/Secret Societies",  # pedo_pedophilia_pedophile_pedophiles (Abuse coverups)
        45: "Alex Jones & Deep State/Secret Societies",  # jones_alex_joe_rogan (Alex Jones, InfoWars)
        52: "Alex Jones & Deep State/Secret Societies",  # qanon_anon_trump_psyop
        63: "Alex Jones & Deep State/Secret Societies",  # pizza_pizzagate_podesta_gate
        72: "Alex Jones & Deep State/Secret Societies",  # freemasonry_mason_freemasons_masons (Illuminati)
        
        # 5. Sci-Fi, Space, UFOs & Esoteric
        35: "Sci-Fi, Space, UFOs & Esoteric",       # moon_nasa_space_apollo
        40: "Sci-Fi, Space, UFOs & Esoteric",       # science_scientific_scientists_universe
        42: "Sci-Fi, Space, UFOs & Esoteric",       # flat_earth_globe_gravity
        51: "Sci-Fi, Space, UFOs & Esoteric",       # aliens_ufo_alien_ufos
        86: "Sci-Fi, Space, UFOs & Esoteric",       # woke_wake_sleep_awake (lucid dreams, astral)
        
        # 6. Environment, Science, Health & Tech
        2: "Environment, Science, Health & Tech",   # vaccine_vaccines_vaccinated_covid
        8: "Environment, Science, Health & Tech",   # food_eat_meat_gmo (GMOs, Monsanto)
        9: "Environment, Science, Health & Tech",   # covid_flu_virus_deaths
        15: "Environment, Science, Health & Tech",  # climate_co2_change_warming
        26: "Environment, Science, Health & Tech",  # masks_mask_wear_wearing
        36: "Environment, Science, Health & Tech",  # vax_vaxxed_anti_vaxx
        55: "Environment, Science, Health & Tech",  # doctor_medical_doctors_dr
        58: "Environment, Science, Health & Tech",  # pharma_cancer_big_pharmaceutical
    }
    
    # Load the topic list from the model
    from bertopic import BERTopic
    model_dir = 'data/processed/bertopic_model_new'
    if not os.path.exists(model_dir):
        raise FileNotFoundError(f"Model not found at {model_dir}")
        
    topic_model = BERTopic.load(model_dir)
    topic_info = topic_model.get_topic_info()
    
    mappings = []
    for idx, row in topic_info.iterrows():
        topic_id = int(row['Topic'])
        
        if topic_id == -1:
            mappings.append({
                'Topic': -1,
                'Topic_Name': 'Outliers',
                'Super_Topic': 'Outliers',
                'Match_Score': 1.0,
                'Keywords': 'outliers, noise'
            })
            continue
            
        topic_words = [word for word, _ in topic_model.get_topic(topic_id)]
        keywords_str = ", ".join(topic_words)
        
        # Determine Super-Topic assignment
        if topic_id in super_topic_assignments:
            assigned_st = super_topic_assignments[topic_id]
            match_score = 1.0  # Explicit manual assignment
        else:
            assigned_st = "Other / General Conspiracy"
            match_score = 0.0  # Default fallback
            
        mappings.append({
            'Topic': topic_id,
            'Topic_Name': row['Name'],
            'Super_Topic': assigned_st,
            'Match_Score': match_score,
            'Keywords': keywords_str
        })
        
    df_map = pd.DataFrame(mappings)
    df_map.to_csv(mapping_path, index=False)
    
    print("\n--- NEW Taxonomy Distribution (Excluding Outlier Topic -1) ---")
    dist = df_map[df_map['Topic'] != -1]['Super_Topic'].value_counts()
    for st, count in dist.items():
        print(f"  * {st:45s}: {count:2d} topics")
        
    print("\nSuccessfully updated to an ultra-precise, logically curated taxonomy mapping!")

if __name__ == '__main__':
    main()

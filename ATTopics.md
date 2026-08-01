# Scientific Report: ATS Topic Transfer Diagnostic & Exploratory HAC Dendrogram

This report presents a clean, honest, and ungenerous empirical evaluation of the transferability of the Reddit-trained topic model (97 fine-grained centroids) onto the historical AboveTopSecret (ATS) corpus (50,000 temporally stratified comments). 

---

## 1. Leaf-Only (0.35) Outlier Rates (The Headline Metric)

This is the primary ungenerous diagnostic. Any comment failing the $0.35$ cosine similarity threshold is strictly categorized as an **Outlier (-1)**. No multi-level fallbacks, parent-branch promotions, or title-rescue logic were used.

| Era | Partition Years | Sample Size | Outliers | Outlier Rate | Median Cosine Similarity (Matched) | Median Cosine Similarity (All) |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **Early** | pre-2008 (2001-2007) | 16,666 | 3,500 | **21.00%** | 0.4624 | 0.4332 |
| **Middle** | classic (2008-2016) | 16,666 | 3,203 | **19.22%** | 0.4723 | 0.4441 |
| **Late** | modern (2017+) | 16,668 | 3,001 | **18.00%** | 0.4856 | 0.4588 |
| **OVERALL** | 2001-2024 | 50,000 | 9,704 | **19.41%** | 0.4738 | 0.4447 |

---

## 2. Top 10 Activated Topics Per Era (Spot-Checking Semantic Drift)

These lists display the most frequent leaf topics activated in each era by comments that successfully cleared the $0.35$ threshold, showing how themes shift historically.

### Early Era (Pre-2008)
- Topic 3: 3_god_jesus_bible_religion (854 hits)\n- Topic 51: 51_aliens_ufo_alien_ufos (796 hits)\n- Topic 10: 10_building_plane_collapse_towers (585 hits)\n- Topic 31: 31_isis_syria_al_islam (566 hits)\n- Topic 23: 23_banned_mods_ban_reddit (449 hits)\n- Topic 75: 75_war_wars_ww3_america (348 hits)\n- Topic 72: 72_freemasonry_mason_freemasons_masons (343 hits)\n- Topic 12: 12_fbi_cia_mueller_assange (324 hits)\n- Topic 44: 44_video_youtube_watch_videos (301 hits)\n- Topic 79: 79_nuclear_nukes_nuke_weapons (288 hits)\n

### Middle Era (2008-2016)
- Topic 3: 3_god_jesus_bible_religion (866 hits)\n- Topic 51: 51_aliens_ufo_alien_ufos (742 hits)\n- Topic 1: 1_money_tax_taxes_pay (521 hits)\n- Topic 10: 10_building_plane_collapse_towers (448 hits)\n- Topic 32: 32_fear_schizophrenia_control_life (417 hits)\n- Topic 31: 31_isis_syria_al_islam (353 hits)\n- Topic 44: 44_video_youtube_watch_videos (333 hits)\n- Topic 0: 0_ha_thanks_thank_lol (303 hits)\n- Topic 84: 84_obama_bush_president_bushes (264 hits)\n- Topic 43: 43_police_cops_cop_officer (254 hits)\n

### Late Era (2017+)
- Topic 12: 12_fbi_cia_mueller_assange (757 hits)\n- Topic 1: 1_money_tax_taxes_pay (562 hits)\n- Topic 50: 50_trump_president_establishment_people (558 hits)\n- Topic 3: 3_god_jesus_bible_religion (508 hits)\n- Topic 0: 0_ha_thanks_thank_lol (489 hits)\n- Topic 5: 5_kamala_hillary_tulsi_pelosi (384 hits)\n- Topic 51: 51_aliens_ufo_alien_ufos (349 hits)\n- Topic 6: 6_russia_ukraine_russian_putin (345 hits)\n- Topic 9: 9_covid_flu_virus_deaths (332 hits)\n- Topic 2: 2_vaccine_vaccines_vaccinated_covid (297 hits)\n

---

## 3. Residual Discovery Pass (Outliers + Ambiguous Pool)

To discover what structure the Reddit model is missing, we pooled the **37,269 comments (74.54% of the sample)** that were either hard outliers ($s_1 < 0.35$) or ambiguous matches ($s_1 < 0.50$ or $s_1 - s_2 < 0.05$). We fit $K=10$ K-Means clusters to find coherent, alternative home-grown themes.

| Cluster ID | Total Size | Early Counts (Pre-2008) | Middle Counts (2008-2016) | Late Counts (2017+) | Highly Concentrated Signature Words (TF-IDF) |
| :---: | :---: | :---: | :---: | :---: | :--- |
| **0** | 3,125 | 643 | 1,128 | 1,354 | *debt, banks, wages, workers, wage, walmart, investment, welfare, inflation, bitcoin, unemployment, poverty* |
| **1** | 5,674 | 2,343 | 1,284 | 2,047 | *setihome, asala, skepticoverlord, upload, uus, pixy, sauron, qpotus, xuenchen, newbie, bigburgh, cleverbot* |
| **2** | 3,608 | 1,271 | 1,085 | 1,252 | *wtc, footage, bates, cops, nist, pentagon, arrest, iraqi, assange, crimes, terrorism, officers* |
| **3** | 4,001 | 1,464 | 1,641 | 896 | *orbit, magnetic, earthquakes, contrail, earths, balloon, footage, venus, telescope, gravity, satellite, galaxy* |
| **4** | 4,041 | 1,482 | 1,629 | 930 | *serpent, christianity, reincarnation, angels, moses, verse, hebrew, gravity, genesis, eternal, mayan, biblical* |
| **5** | 3,394 | 954 | 762 | 1,678 | *democrats, hillary, kerry, republicans, mccain, congress, trumps, supporters, bushs, biden, saddam, impeachment* |
| **6** | 2,952 | 1,478 | 837 | 637 | *missiles, missile, carrier, bomber, afghanistan, syria, carriers, armed, iraqi, deployment, raf, rounds* |
| **7** | 3,558 | 987 | 1,395 | 1,176 | *muslims, marriage, democracy, christianity, terrorism, homosexuality, amendment, freedoms, hatred, sharia, atheist, atheists* |
| **8** | 4,282 | 1,042 | 1,459 | 1,781 | *vitamin, symptoms, doctors, bees, insulin, healthy, gravity, diet, alcohol, sugar, patients, protein* |
| **9** | 2,634 | 1,361 | 1,224 | 49 | *enjoies, riaa, maybemaybe, pacsade, bodrul, delete, gimpsavvycom, ascap, joel, cuhail, zelong, plagiarism* |

---

## 4. Exploratory Reddit Topic Tree Dendrogram

The following hierarchical structure was built by running Agglomerative Hierarchical Clustering (average linkage, cosine distance) on the 97 Reddit centroids. It is purely visual and is not wired into any classification logic.

```markdown
- **Branch (merge dist: 0.765)** | *god, jesus, bible, religion, satan, church, christ, christian*
  - **Branch (merge dist: 0.748)** | *god, jesus, bible, religion, satan, church, christ, christian*
    - **Branch (merge dist: 0.486)** | *god, jesus, bible, religion, satan, church, christ, christian*
      - **Topic 3: 3_god_jesus_bible_religion** *(keywords: god, jesus, bible, religion, satan, church, christ, christian, christianity, believe)*
      - **Topic 72: 72_freemasonry_mason_freemasons_masons** *(keywords: freemasonry, mason, freemasons, masons, masonic, freemason, illuminati, secret, societies, skull)*
    - **Branch (merge dist: 0.673)** | *movie, film, movies, imdb, watched, watch, episode, watching*
      - **Branch (merge dist: 0.621)** | *movie, film, movies, imdb, watched, watch, episode, watching*
        - **Branch (merge dist: 0.468)** | *movie, film, movies, imdb, watched, watch, episode, watching*
          - **Topic 49: 49_movie_film_movies_imdb** *(keywords: movie, film, movies, imdb, watched, watch, episode, watching, netflix, liked)*
          - **Topic 83: 83_book_books_read_reading** *(keywords: book, books, read, reading, thanks, novel, amazon, shakespeare, buy, interesting)*
        - **Branch (merge dist: 0.568)** | *music, song, album, hip, lyrics, hop, songs, rap*
          - **Topic 57: 57_music_song_album_hip** *(keywords: music, song, album, hip, lyrics, hop, songs, rap, rappers, band)*
          - *[Truncated 2 topics: 44_video_youtube_watch_videos, 61_youtu_https_youtube_watch...]*
      - **Branch (merge dist: 0.641)** | *fake, real, legit, looks, fakes, isn, picture, genuine*
        - **Branch (merge dist: 0.557)** | *fake, real, legit, looks, fakes, isn, picture, genuine*
          - **Topic 62: 62_fake_real_legit_looks** *(keywords: fake, real, legit, looks, fakes, isn, picture, genuine, seen, thing)*
          - **Topic 89: 89_face_nose_look_pants** *(keywords: face, nose, look, pants, head, looks, resemblance, chin, ass, dress)*
        - **Branch (merge dist: 0.602)** | *kamala, hillary, tulsi, pelosi, like, woman, lady, did*
          - **Topic 5: 5_kamala_hillary_tulsi_pelosi** *(keywords: kamala, hillary, tulsi, pelosi, like, woman, lady, did, just, think)*
          - *[Truncated 5 topics: 85_elon_musk_billionaire_nazi, 22_epstein_trump_maxwell_jeffrey, 60_suicide_dead_death_alive...]*
  - **Branch (merge dist: 0.755)** | *phone, phones, cameras, camera, footage, apple, wifi, detection*
    - **Branch (merge dist: 0.509)** | *phone, phones, cameras, camera, footage, apple, wifi, detection*
      - **Topic 33: 33_phone_phones_cameras_camera** *(keywords: phone, phones, cameras, camera, footage, apple, wifi, detection, gps, data)*
      - **Topic 47: 47_google_search_results_apps** *(keywords: google, search, results, apps, app, cloud, b4, searches, use, aspx)*
    - **Branch (merge dist: 0.744)** | *ss, concentration, title, post, sorry, sensitive, visibility, division*
      - **Branch (merge dist: 0.718)** | *ss, concentration, title, post, sorry, sensitive, visibility, division*
        - **Branch (merge dist: 0.696)** | *ss, concentration, title, post, sorry, sensitive, visibility, division*
          - *[Truncated 13 topics: 96_ss_concentration_title_post, 20_numbers_number_statistics_math, 54_bot_bots_account_shills...]*
          - *[Truncated 35 topics: 42_flat_earth_globe_gravity, 35_moon_nasa_space_apollo, 51_aliens_ufo_alien_ufos...]*
        - **Branch (merge dist: 0.697)** | *money, tax, taxes, pay, income, debt, currency, bitcoin*
          - *[Truncated 9 topics: 1_money_tax_taxes_pay, 95_oil_gas_prices_price, 15_climate_co2_change_warming...]*
          - *[Truncated 7 topics: 11_white_black_racist_racism, 80_slavery_slaves_slave_states, 29_court_guilty_judges_judge...]*
      - **Branch (merge dist: 0.719)** | *food, eat, meat, gmo, eating, organic, monsanto, foods*
        - **Branch (merge dist: 0.659)** | *food, eat, meat, gmo, eating, organic, monsanto, foods*
          - **Topic 8: 8_food_eat_meat_gmo** *(keywords: food, eat, meat, gmo, eating, organic, monsanto, foods, milk, chicken)*
          - *[Truncated 8 topics: 14_drugs_weed_drug_marijuana, 58_pharma_cancer_big_pharmaceutical, 55_doctor_medical_doctors_dr...]*
        - **Branch (merge dist: 0.670)** | *fear, schizophrenia, control, life, psychosis, mental, paranoid, paranoia*
          - *[Truncated 2 topics: 32_fear_schizophrenia_control_life, 86_woke_wake_sleep_awake...]*
          - *[Truncated 5 topics: 38_abortion_baby_abortions_babies, 21_kids_school_children_parents, 19_gay_trans_gender_women...]*

```


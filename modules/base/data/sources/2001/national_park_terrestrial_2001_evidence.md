# National park and protected-area evidence for 2001

`national_park_terrestrial_2001_evidence.tsv` records evidence for country or territory gaps in the UNSD 2000 terrestrial protected-area snapshot, plus sourced national-park-only values for the 2001 scenario. The historical-data importer reads this ledger.

## Measures and safe use

- `national_park_land_area_km2` is the sum of formally designated terrestrial national-park areas for the 2001 scenario. Marine area is excluded.
- `national_park_land_coverage_pct` is that park area divided by the 2001 land-area denominator shown in `denominator_source_url`. It is a parks-only measure.
- `terrestrial_protected_area_pct_2000_override` is reserved for a defensible value matching the broader UNSD category: nationally designated terrestrial protected areas, across categories, for observation year 2000. Maldives has a derived zero from its official register's designation dates and site types; Nauru has a contemporaneous April 2000 report stating that no terrestrial reserves were set aside.
- Blank numeric cells mean no comparable value was established. They must remain unavailable rather than be normalized to zero.

Do not load the park-only values for Kosovo, Montenegro, or Taiwan into `terrestrial_protected_area_pct_2000`: national parks are only a subset of all protected-area categories, and their reference year and denominator differ from the UNSD series. The same distinction applies to the 2001 park-only zeroes for Maldives and São Tomé and Príncipe. Nauru's separate broad-field override is reported for observation year 2000; its park-specific zero uses the same contemporaneous no-reserves evidence. A derived or reported zero is explicitly different from a missing value.

## Supported values

### Kosovo

The Kosovo Environmental Protection Agency says Sharr National Park was declared in 1986 and has a statutory area of 39,000 ha. Kosovo's statistical annex for 2001 reports a total territory of 10,887 km², giving a derived parks-only land coverage of 3.5823%. The park's operations were suspended from 1999 through 2002, so the area records its legal designation, not active management. A later biodiversity assessment reports 46,247.3 ha across several protection categories; because it is later and not a 2000 observation, it is not an override for the UNSD field.

Sources: [KEPA Sharr National Park](https://ammk-rks.net/en/drejtorite/30/drejtoria-parku-kombetar-sharr), [Kosovo 2005 progress report, 2001 area row](https://integrimievropian.rks-gov.net/wp-content/uploads/2022/11/kosovo_progress_report_2005.pdf), and [Kosovo Biodiversity Assessment](https://ammk-rks.net/assets/cms/uploads/files/Publikime-raporte/Kosovo-BiodiversityAssessment.pdf).

### Maldives

The environment ministry's dated register lists 15 reef sites protected in 1995 and ten further marine sites protected in 1999. The first listed terrestrial wetland is dated 2004. On that official register, the defensible 2000 terrestrial-only protected-area share and terrestrial national-park area are zero. This is derived from the register, not directly reported by UNSD; the provenance and derivation are preserved in the TSV.

Source: [Maldives Ministry of Climate Change, Environment and Energy, Protected Areas of the Maldives, updated August 2024](https://mote.gov.mv/wp-content/files/Protected_Areas_List_Updated_Aug_2024.pdf).

### São Tomé and Príncipe

The CBD national report states that Obô de São Tomé and Obô do Príncipe Natural Parks were established under Laws 6/2006 and 7/2006. That supports zero formally designated national-park area in 2001. It does not establish zero for every protected-area category: the country also had separate forestry legislation, so the broader UNSD-compatible percentage remains blank.

Source: [CBD Sixth National Report of São Tomé and Príncipe](https://www.cbd.int/doc/nr/nr-06/st-nr-06-en.pdf).

### Nauru

The Pacific Community (SPC/SOPAC) environmental-vulnerability field report for April 2000 states that Nauru had no terrestrial or marine reserves set aside for environmental management or refugia. This is direct contemporaneous evidence for a zero nationally designated terrestrial protected-area proportion in 2000 and zero designated terrestrial national-park area. Nauru's 1996 National Environmental Management Strategy independently identifies candidate conservation sites as future proposals, and the later CBD national report says no protected area had been gazetted. Candidate sites are not counted as protected areas or national parks.

Sources: [Environmental vulnerability index Nauru data profile: summary trip report (April 2000)](https://spccfpstore1.blob.core.windows.net/digitallibrary-docs/files/71/71445f1b5a59f2d843955a1baa0d9d08.pdf), [Nauru National Environmental Management Strategy and National Environmental Action Plan (1996)](https://policy.asiapacificenergy.org/sites/default/files/NEMS%20and%20NEAP%201996%20%28EN%29.pdf), and [CBD Sixth National Report of Nauru](https://www.cbd.int/doc/nr/nr-06/nr-nr-06-en.pdf).

### Taiwan

The government statistical profile for the end of 2001 reports six national parks. Summing their terrestrial areas and excluding Kenting's separately tabulated marine area gives 307,659 ha (3,076.59 km²). The official 2001 land-area denominator is 36,188.04 km², producing a parks-only share of 8.5017%.

Sources: [Taiwan's 2001 national-park profile](https://ws.ndc.gov.tw/Download.ashx?icon=..pdf&n=OTFfUERGLnBkZg%3D%3D&u=LzAwMS9hZG1pbmlzdHJhdG9yLzEwL3JlbGZpbGUvMC8xNDE3Mi80ZjIxY2ViYy1kYTg5LTQzNTMtOTRkYy0zOTkzMjUwZGUxNmYucGRm) and [DGBAS Statistical Yearbook, 2001 land area](https://ws.dgbas.gov.tw/001/Upload/466/ebook/ebook_90360/pdf/full.pdf).

## Rows intentionally left without a 2001 numeric value

- **Antarctica (ATA):** it is not a sovereign country-level unit for this measure. The Antarctic Treaty Secretariat documents both the sovereignty-claim framework and Antarctic Specially Protected/Managed Areas; these are Treaty-system sites, not national parks belonging to a country. Sources: [Antarctic Treaty](https://www.ats.aq/e/antarctictreaty.html) and [ATS protected-area database description](https://www.ats.aq/e/tools-and-resources.html).
- **Palestine (PSE):** PCBS's 2000 Statistical Abstract reports 54.4 km² across 19 natural reserves as the Palestinian Territory total; all 19 are listed in the West Bank and the Gaza row is blank. Its scope footnote says the data include only reserves controlled by the Palestinian National Authority. The companion 2001–2002 release says the approximate 54 km²/19-reserve count was unchanged from the prior year. Both observations are retained separately in `palestinian_natural_reserves_2001_candidate.tsv`. A separately reported Wadi Gaza designation in June 2000 and the PNA-only scope mean this is not an exhaustive all-authority protected-area inventory. It does not establish a national-parks-only total or a comparable all-category UNSD percentage; those fields remain unavailable. PCBS/EQA also cite a 2014 plan showing 51,157 ha of West Bank natural reserves, including East Jerusalem; it is not a 2001 measurement. A UN report records that protected-area planning was suspended in 2000. Sources: [PCBS 2000 Statistical Abstract](https://www.pcbs.gov.ps/Downloads/book850.pdf), [PCBS 2001–2002 release](https://www.pcbs.gov.ps/Portals/_pcbs/PressRelease/lus_e.html), [UNESCO Wadi Gaza](https://whc.unesco.org/en/tentativelists/5722/), [PCBS/EQA](https://www.pcbs.gov.ps/en/post-details/?postId=20078), and [UN report on the occupied Palestinian territory](https://www.un.org/unispal/document/auto-insert-203995/).
- **San Marino (SMR):** its later CBD biodiversity strategy describes protected-natural-area planning zones covering 39% of territory under laws dating to 1992 and 1995. It gives no 2001 observation or national-parks-only area; the 39% figure is therefore retained as context only. Source: [San Marino CBD NBSAP](https://www.cbd.int/doc/world/sm/sm-nbsap-01-en.pdf).
- **South Sudan (SSD):** South Sudan became independent in 2011. The Sudan government's 2004 Dinder National Park Management Plan, Table 4, lists Southern National Park (1939, 2,300,000 ha), Nimule (1945, 41,000 ha), Boma (1986, 2,280,000 ha), Bandingilo (1986, 1,650,000 ha), and Shambe (1985, 62,000 ha) in a Sudan-wide roster. The 2018 South Sudan CBD strategy reports different area/classification information and proposed changes. These sources do not establish a 2001 South Sudan-only park total or compatible territorial denominator. The numeric fields remain blank rather than summing or backcasting the Sudan-wide list. Sources: [United Nations Member States profile](https://www.un.org/en/about-us/member-states/south-sudan), [Sudan 2004 Dinder National Park Management Plan, Table 4](https://hcenr.gov.sd/en/wp-content/uploads/2021/01/Dinder-Management-plan-2004.pdf), and [South Sudan CBD NBSAP, 2018–2027](https://www.cbd.int/doc/world/ss/ss-nbsap-01-en.pdf).
- **Vatican City (VAT):** the Vatican Museums report that the Vatican Gardens cover about 22 ha, but garden area is not evidence of national-park designation or a 2001 protected-area aggregate. The area is not converted into a protected-area value. Source: [Vatican Gardens](https://www.museivaticani.va/content/museivaticani/en/patrimonio-naturale-archeologico/giardini/presentazione-giardini/giardini.html).

## Integration note

The values in this ledger that can fill the broad `terrestrial_protected_area_pct_2000` field are Maldives' derived `0.0000`, provided the importer identifies its register-based derivation, and Nauru's reported `0.0000` for observation year 2000, sourced to the contemporaneous SPC/SOPAC field report. Kosovo's, Montenegro's, and Taiwan's values belong in a distinct national-park field or a UI explicitly labeled as national-park coverage. São Tomé and Príncipe's zero is parks-only. Other rows should remain unavailable or not applicable until a dated, comparable source is found.

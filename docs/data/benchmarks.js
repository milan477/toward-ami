window.__AMI_DATA__ = window.__AMI_DATA__ || {};
window.__AMI_DATA__["benchmarks"] = [
 {
  "name": "NSynth",
  "extended": "Neural Audio Synthesis of Musical Notes with WaveNet Autoencoders",
  "paper_title": "Neural Audio Synthesis of Musical Notes with WaveNet Autoencoders",
  "domain": "Focused",
  "format": "MCL",
  "year": "2017",
  "modalities": "Music",
  "skills": "Instrument source (acoustic, electronics, synthetic), pitch, note quality (bright, dark, decay, …), and family (instrument type)",
  "sources": "",
  "size": "305979",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/pdf/1704.01279"
   },
   {
    "label": "magenta.withgoogle.com",
    "url": "https://magenta.withgoogle.com/datasets/nsynth"
   }
  ],
  "paper_url": "https://arxiv.org/pdf/1704.01279",
  "hf_url": "",
  "code_url": "",
  "bibtex": "@misc{nsynth2017,\n    Author = {Jesse Engel and Cinjon Resnick and Adam Roberts and\n              Sander Dieleman and Douglas Eck and Karen Simonyan and\n              Mohammad Norouzi},\n    Title = {Neural Audio Synthesis of Musical Notes with WaveNet Autoencoders},\n    Year = {2017},\n    Eprint = {arXiv:1704.01279},\n}",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "MARBLE",
  "extended": "MARBLE: Music Audio Representation Benchmark  for Universal Evaluation",
  "paper_title": "MARBLE: Music Audio Representation Benchmark  for Universal Evaluation",
  "domain": "Multi-task",
  "format": "Task-specificQ",
  "year": "2023",
  "modalities": "Music",
  "skills": "18 tasks across 4 hierarchy levels (acoustic, performance, score, high-level description): Key Detection, Music Tagging, Genre Classification, Emotion Detection, Score-level Pitch Classification, Beat Tracking, Melody Extraction, Chord Estimation, Lyrics Transcription, Vocal Technique Detection, Singer Identification, Instrument Classification, Source Separation",
  "sources": "12 datasets: Giantsteps key, MagnaTagATune, MTG Top50, GTZAN, MTG Genre, Emomusic, MTG MoodTheme, Nsynth, GTZAN Rhythm, MelodyDB, GuitarSet, MulJam2.0, Jamendo, VocalSet, MUSDB18",
  "size": "",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2306.10548"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/a43992899/MARBLE-Benchmark"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2306.10548",
  "hf_url": "",
  "code_url": "https://github.com/a43992899/MARBLE-Benchmark",
  "bibtex": "@misc{yuanMARBLEMusicAudio2023,\n  title = {{{MARBLE}}: {{Music Audio Representation Benchmark}} for {{Universal Evaluation}}},\n  shorttitle = {{{MARBLE}}},\n  author = {Yuan, Ruibin and Ma, Yinghao and Li, Yizhi and Zhang, Ge and Chen, Xingran and Yin, Hanzhi and Zhuo, Le and Liu, Yiqi and Huang, Jiawen and Tian, Zeyue and Deng, Binyue and Wang, Ningzhi and Lin, Chenghua and Benetos, Emmanouil and Ragni, Anton and Gyenge, Norbert and Dannenberg, Roger and Chen, Wenhu and Xia, Gus and Xue, Wei and Liu, Si and Wang, Shi and Liu, Ruibo and Guo, Yike and Fu, Jie},\n  year = 2023,\n  month = nov,\n  number = {arXiv:2306.10548},\n  eprint = {2306.10548},\n  primaryclass = {cs},\n  publisher = {arXiv},\n  doi = {10.48550/arXiv.2306.10548},\n  archiveprefix = {arXiv},\n}",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "MMAU",
  "extended": "Massive Multi-Task Audio Understanding And Reasoning Benchmark",
  "paper_title": "MMAU: A Massive Multi-Task Audio Understanding And Reasoning Benchmark",
  "domain": "Multi-Task",
  "format": "MCQ",
  "year": "2024",
  "modalities": "Sound, Speech, Music",
  "skills": "27 Skills Across Information Extraction And Reasoning. Information Extraction: Eco-Acoustic Knowledge, Sound-Based Event Recognition, Melodic Structure Interpretation, Harmony And Chord Progressions, Rhythm And Tempo Understanding, Instrumentation, Musical Texture Interpretation, Event-Based Knowledge Retrieval, Phonemic Stress Pattern Analysis, Conversational Fact Retrieval, Key Highlight Extraction. Reasoning: Temporal Event Reasoning, Event-Based Sound Reasoning, Ambient Sound Interpretation, Acoustic Source Inference, Acoustic Scene Reasoning, Emotional Tone Interpretation, Temporal Reasoning, Musical Genre Reasoning, Lyrical Reasoning, Socio-Cultural Interpretation, Emotion Flip Detection, Multi Speaker Role Mapping, Emotion State Summarisation, Counting, Dissonant Emotion Interpretation",
  "sources": "Pooled From Several Datasets: Audioset (2788), Audioset Strong (391), Mustard (405), MELD (540), Voxceleb-1 (633), IEMOCAP (515), Musicbench (1937), Jamendo (32), SDD (277), Musiccaps (514), Guitarset (506), MUSDB18 (68), Synthetic (1394)",
  "size": "10000",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2410.19168"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/gamma-lab-umd/MMAU-test-mini"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/gamma-lab-umd/MMAU-test"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/Sakshi113/MMAU"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2410.19168",
  "hf_url": "https://huggingface.co/datasets/gamma-lab-umd/MMAU-test-mini",
  "code_url": "https://github.com/Sakshi113/MMAU",
  "bibtex": "@misc{sakshiMMAUMassiveMultiTask2024,\n  title = {{{MMAU}}: {{A Massive Multi-Task Audio Understanding}} and {{Reasoning Benchmark}}},\n  shorttitle = {{{MMAU}}},\n  author = {Sakshi, S. and Tyagi, Utkarsh and Kumar, Sonal and Seth, Ashish and Selvakumar, Ramaneswaran and Nieto, Oriol and Duraiswami, Ramani and Ghosh, Sreyan and Manocha, Dinesh},\n  year = 2024,\n  month = oct,\n  number = {arXiv:2410.19168},\n  eprint = {2410.19168},\n  primaryclass = {eess},\n  publisher = {arXiv},\n  doi = {10.48550/arXiv.2410.19168},\n  archiveprefix = {arXiv},\n}",
  "status": "confirmed",
  "question_count": 334,
  "has_questions": true,
  "questions_url": "data/questions/mmau.json"
 },
 {
  "name": "MuChoMusic",
  "extended": "Evaluating Music Understanding in Multimodal Audio-Language Models",
  "paper_title": "Evaluating Music Understanding in Multimodal Audio-Language Models",
  "domain": "Multi-task",
  "format": "MCQ",
  "year": "2024",
  "modalities": "Music",
  "skills": "Music knowledge (Performance Metre and Rhythm, Sound Texture Melody Harmony Structure, Instrumentation) and reasoning (Mood & Expression Genre & Style, FunctionalContext TemporalRelations Lyrics Cultural Conte)",
  "sources": "MusicCaps and the Song Describer Dataset",
  "size": "1187",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2408.01337"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/mulab-mir/muchomusic"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/mulab-mir/muchomusic"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2408.01337",
  "hf_url": "https://huggingface.co/datasets/mulab-mir/muchomusic",
  "code_url": "https://github.com/mulab-mir/muchomusic",
  "bibtex": "@misc{weckMuChoMusicEvaluatingMusic2024,\n  title = {{{MuChoMusic}}: {{Evaluating Music Understanding}} in {{Multimodal Audio-Language Models}}},\n  shorttitle = {{{MuChoMusic}}},\n  author = {Weck, Benno and Manco, Ilaria and Benetos, Emmanouil and Quinton, Elio and Fazekas, George and Bogdanov, Dmitry},\n  year = 2024,\n  month = aug,\n  number = {arXiv:2408.01337},\n  eprint = {2408.01337},\n  primaryclass = {cs},\n  publisher = {arXiv},\n  doi = {10.48550/arXiv.2408.01337},\n  archiveprefix = {arXiv},\n}",
  "status": "confirmed",
  "question_count": 1187,
  "has_questions": true,
  "questions_url": "data/questions/muchomusic.json"
 },
 {
  "name": "OpenMU",
  "extended": "OpenMU: Your Swiss Army Knife for Music Understanding",
  "paper_title": "OpenMU: Your Swiss Army Knife for Music Understanding",
  "domain": "Multi-task",
  "format": "Open-ended QA / Multiple Choice",
  "year": "2024",
  "modalities": "Music",
  "skills": "Music captioning, music reasoning, lyrics understanding, tool using, multiple-choice QA",
  "sources": "MusicCaps, MusicInstruct, LPMusicCaps, LPMusicMTT, Music4all, MusicQA-Fin, MusicQA-Test, GTZAN, MusicNet, MTT, MTG-Jamendo, BART-Fusion, Tool-Using, MuChoMusic\n(Some with new annotations)",
  "size": "221429 clips; >1,000,000 questions",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2410.15573"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/Sony/OpenMU-Bench"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/sony/openmu"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2410.15573",
  "hf_url": "https://huggingface.co/datasets/Sony/OpenMU-Bench",
  "code_url": "https://github.com/sony/openmu",
  "bibtex": "@article{zhao2024openmu,\n  title={OpenMU: Your Swiss Army Knife for Music Understanding},\n  author={Zhao, Mengjie and Zhong, Zhi and Mao, Zhuoyuan and Yang, Shiqi and Liao, Wei-Hsiang and Takahashi, Shusuke and Wakaki, Hiromi and Mitsufuji, Yuki},\n  journal={arXiv preprint arXiv:2410.15573},\n  year={2024}\n}",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "Percepiano",
  "extended": "Piano Performance Evaluation Dataset with Multi-level Perceptual Features",
  "paper_title": "Piano performance evaluation dataset with multilevel perceptual features",
  "domain": "Focused",
  "format": "Multi-class",
  "year": "2024",
  "modalities": "Piano performance evaluation",
  "skills": "Interpretation and perceptual features",
  "sources": "",
  "size": "",
  "models": "",
  "links": [
   {
    "label": "Nature",
    "url": "https://www.nature.com/articles/s41598-024-73810-0"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/JonghoKimSNU/PercePiano"
   }
  ],
  "paper_url": "https://www.nature.com/articles/s41598-024-73810-0",
  "hf_url": "",
  "code_url": "https://github.com/JonghoKimSNU/PercePiano",
  "bibtex": "",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "CMI-Bench",
  "extended": "CMI-Bench: A Comprehensive Benchmark for Evaluating Music Instruction Following",
  "paper_title": "CMI-Bench: A Comprehensive Benchmark for Evaluating Music Instruction Following",
  "domain": "Multi-Task",
  "format": "Task-SpecificQ",
  "year": "2025",
  "modalities": "Music",
  "skills": "14 Tasks Spanning Multi-Class, Multi-Label, Regression, Captioning, and Sequential Prediction",
  "sources": "20 Datasets: GS, EMO, MagnaTagATune, MTG-Top50, MTG-Instrument, Nsynth-Instrument, MTG-Genre, GTZAN, MTG-Emotion, Nsynth-Pitch, VocalSet, SDD, MusicCaps, DSing, GTZAN-Rhythm, Ballroom, GTZAN-Rhythm (DownBeat), Ballroom (DownBeat), MedleyDB v2, GuZheng_99",
  "size": "",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2506.12285"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/nicolaus625/CMI-bench"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/nicolaus625/CMI-bench/tree/main"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2506.12285",
  "hf_url": "https://huggingface.co/datasets/nicolaus625/CMI-bench",
  "code_url": "https://github.com/nicolaus625/CMI-bench/tree/main",
  "bibtex": "@misc{maCMIBenchComprehensiveBenchmark2025,\n  title = {{{CMI-Bench}}: {{A Comprehensive Benchmark}} for {{Evaluating Music Instruction Following}}},\n  shorttitle = {{{CMI-Bench}}},\n  author = {Ma, Yinghao and Li, Siyou and Yu, Juntao and Benetos, Emmanouil and Maezawa, Akira},\n  year = 2025,\n  month = jun,\n  number = {arXiv:2506.12285},\n  eprint = {2506.12285},\n  primaryclass = {eess},\n  publisher = {arXiv},\n  doi = {10.48550/arXiv.2506.12285},\n  archiveprefix = {arXiv},\n}",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "MMAR",
  "extended": "MMAR: A Challenging Benchmark for Deep Reasoning in Speech, Audio, Music, and Their Mix",
  "paper_title": "MMAR: A Challenging Benchmark for Deep Reasoning in Speech, Audio, Music, and Their Mix",
  "domain": "Multi-task",
  "format": "MCQ",
  "year": "2025",
  "modalities": "Sound, music, speech, and their mixes",
  "skills": "16 skills across Signal, Perception, and Semantic & Cultural: Acoustic Quality Analysis, Anomaly Detection, Audio Difference Analysis, Spatial Analysis, Temporal Analysis, Correlation Analysis, Counting and Statistics, Music Theory, Environmental Perception and Reasoning, Content Analysis, Emotion and Intention, Speaker Analysis, Culture of Speaker, Imagination, Aesthetic Analysis, Professional Knowledge & Reasoning",
  "sources": "Real-world internet videos",
  "size": "323 music-related questions (1,000 in total)",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2505.13032"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/BoJack/MMAR"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/ddlBoJack/MMAR"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2505.13032",
  "hf_url": "https://huggingface.co/datasets/BoJack/MMAR",
  "code_url": "https://github.com/ddlBoJack/MMAR",
  "bibtex": "@misc{maMMARChallengingBenchmark2025,\n  title = {{{MMAR}}: {{A Challenging Benchmark}} for {{Deep Reasoning}} in {{Speech}}, {{Audio}}, {{Music}}, and {{Their Mix}}},\n  shorttitle = {{{MMAR}}},\n  author = {Ma, Ziyang and Ma, Yinghao and Zhu, Yanqiao and Yang, Chen and Chao, Yi-Wen and Xu, Ruiyang and Chen, Wenxi and Chen, Yuanzhe and Chen, Zhuo and Cong, Jian and Li, Kai and Li, Keliang and Li, Siyou and Li, Xinfeng and Li, Xiquan and Lian, Zheng and Liang, Yuzhe and Liu, Minghao and Niu, Zhikang and Wang, Tianrui and Wang, Yuping and Wang, Yuxuan and Wu, Yihao and Yang, Guanrou and Yu, Jianwei and Yuan, Ruibin and Zheng, Zhisheng and Zhou, Ziya and Zhu, Haina and Xue, Wei and Benetos, Emmanouil and Yu, Kai and Chng, Eng-Siong and Chen, Xie},\n  year = 2025,\n  month = may,\n  number = {arXiv:2505.13032},\n  eprint = {2505.13032},\n  primaryclass = {cs},\n  publisher = {arXiv},\n  doi = {10.48550/arXiv.2505.13032},\n  archiveprefix = {arXiv},\n}",
  "status": "confirmed",
  "question_count": 323,
  "has_questions": true,
  "questions_url": "data/questions/mmar.json"
 },
 {
  "name": "MMAU-Pro",
  "extended": "Massive Multitask Audio Understanding and Reasoning Benchmark — Pro",
  "paper_title": "MMAU-Pro: A Challenging and Comprehensive Benchmark for Holistic Evaluation of Audio General Intelligence",
  "domain": "Multi-task",
  "format": "MCQ, OEQ",
  "year": "2025",
  "modalities": "Sound, music, speech, mix",
  "skills": "49 skills across perceptual and reasoning categories",
  "sources": "“from the wild”",
  "size": "5305",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2508.13992"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/gamma-lab-umd/MMAU-Pro"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/sonalkum/MMAUPro"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2508.13992",
  "hf_url": "https://huggingface.co/datasets/gamma-lab-umd/MMAU-Pro",
  "code_url": "https://github.com/sonalkum/MMAUPro",
  "bibtex": "@misc{kumarMMAUProChallengingComprehensive2025,\n  title = {{{MMAU-Pro}}: {{A Challenging}} and {{Comprehensive Benchmark}} for {{Holistic Evaluation}} of {{Audio General Intelligence}}},\n  shorttitle = {{{MMAU-Pro}}},\n  author = {Kumar, Sonal and Sedl{\\'a}{\\v c}ek, {\\v S}imon and Lokegaonkar, Vaibhavi and L{\\'o}pez, Fernando and Yu, Wenyi and Anand, Nishit and Ryu, Hyeonggon and Chen, Lichang and Pli{\\v c}ka, Maxim and Hlav{\\'a}{\\v c}ek, Miroslav and Ellingwood, William Fineas and Udupa, Sathvik and Hou, Siyuan and Ferner, Allison and Barahona, Sara and Bola{\\~n}os, Cecilia and Rahi, Satish and {Herrera-Alarc{\\'o}n}, Laura and Dixit, Satvik and Patil, Siddhi and Deshmukh, Soham and Koroshinadze, Lasha and Liu, Yao and Perera, Leibny Paola Garcia and Zanou, Eleni and Stafylakis, Themos and Chung, Joon Son and Harwath, David and Zhang, Chao and Manocha, Dinesh and {Lozano-Diez}, Alicia and Kesiraju, Santosh and Ghosh, Sreyan and Duraiswami, Ramani},\n  year = 2025,\n  month = aug,\n  number = {arXiv:2508.13992},\n  eprint = {2508.13992},\n  primaryclass = {eess},\n  publisher = {arXiv},\n  doi = {10.48550/arXiv.2508.13992},\n  archiveprefix = {arXiv},\n}",
  "status": "confirmed",
  "question_count": 1521,
  "has_questions": true,
  "questions_url": "data/questions/mmaupro.json"
 },
 {
  "name": "MUSE",
  "extended": "Music Understanding And Structural Evaluation Benchmark",
  "paper_title": "The MUSE Benchmark: Probing Music Perception And Auditory Relational Reasoning In Audio Llms",
  "domain": "Low-Level Tasks",
  "format": "MCQ",
  "year": "2025",
  "modalities": "Music",
  "skills": "10 Skills Across Beginner And Advanced Levels. Beginner: Pitch Shift Detection, Rhythm Matching, Oddball Detection, Instrument Id, Melody Shape Id. Advanced: Chord Identification, Syncopation, Key Modulation, Chord Seq. Matching, Meter Identification",
  "sources": "Self-Composed And Recorded",
  "size": "200 Stimuli",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2510.19055"
   },
   {
    "label": "Airtable",
    "url": "https://airtable.com/appQCPXVEeadwacMP/shrHV0OjuwxYBzJ78"
   },
   {
    "label": "GitHub",
    "url": "https://github.com/brandoncarone/MUSE_music_benchmark"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2510.19055",
  "hf_url": "",
  "code_url": "https://github.com/brandoncarone/MUSE_music_benchmark",
  "bibtex": "@misc{caroneMUSEBenchmarkProbing2025,\n  title = {The {{MUSE Benchmark}}: {{Probing Music Perception}} and {{Auditory Relational Reasoning}} in {{Audio LLMS}}},\n  shorttitle = {The {{MUSE Benchmark}}},\n  author = {Carone, Brandon James and Roman, Iran R. and Ripoll{\\'e}s, Pablo},\n  year = 2025,\n  month = oct,\n  number = {arXiv:2510.19055},\n  eprint = {2510.19055},\n  primaryclass = {cs},\n  publisher = {arXiv},\n  doi = {10.48550/arXiv.2510.19055},\n  archiveprefix = {arXiv},\n}",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "Factual Music Comprehension Benchmark",
  "extended": "Assessing Factual Music Comprehension In Large Audio Language Models",
  "paper_title": "Assessing Factual Music Comprehension In Large Audio Language Models",
  "domain": "Multi-Task",
  "format": "",
  "year": "2026",
  "modalities": "",
  "skills": "Six Tasks: Instrument, Composer, Genre, Regional Style, Mood, Time Signature",
  "sources": "Musicnet, The Free Music Archive, And Overclocked Remix.",
  "size": "",
  "models": "",
  "links": [],
  "paper_url": "",
  "hf_url": "",
  "code_url": "",
  "bibtex": "@online{linAssessingFactualMusic2026,\n  title = {Assessing {{Factual Music Comprehension}} in {{Large Audio Language Models}}},\n  author = {Lin, Daniel Chenyu and Freeman, Michael and Thickstun, John},\n  date = {2026-05-26},\n  eprint = {2511.05550},\n  eprinttype = {arXiv},\n  eprintclass = {cs.SD},\n  doi = {10.48550/arXiv.2511.05550},\n  url = {http://arxiv.org/abs/2511.05550},\n  pubstate = {prepublished},\n}",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "HumMusQA",
  "extended": "HumMusQA: A Human-written Music Understanding QA Benchmark Dataset",
  "paper_title": "HumMusQA: A Human-written Music Understanding QA Benchmark Dataset",
  "domain": "Multi-task",
  "format": "MCQ",
  "year": "2026",
  "modalities": "Music",
  "skills": "13 categories",
  "sources": "Hand-crafted",
  "size": "320",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "http://arxiv.org/abs/2603.27877"
   },
   {
    "label": "doi.org",
    "url": "https://doi.org/10.5281/zenodo.18462524"
   }
  ],
  "paper_url": "http://arxiv.org/abs/2603.27877",
  "hf_url": "",
  "code_url": "",
  "bibtex": "@inproceedings{weck-etal-2026-hummusqa, title = {HumMusQA: A Human-written Music Understanding QA Benchmark Dataset}, author = {Weck, Benno and Puentes, Pablo and Poltronieri, Andrea and Prabhu, Satyajeet and Bogdanov, Dmitry}, booktitle = {Proceedings of the 4th Workshop on NLP for Music and Audio}, year = {2026}, pages = {58--67}, doi = {10.18653/v1/2026.nlp4musa-1.9}, url = {https://aclanthology.org/2026.nlp4musa-1.9/}}",
  "status": "confirmed",
  "question_count": 320,
  "has_questions": true,
  "questions_url": "data/questions/hummusqa.json"
 },
 {
  "name": "MuseBench",
  "extended": "/",
  "paper_title": "MuseAgent-1: Interactive Grounded Multimodal Understanding of Music  Scores and Performance Audio",
  "domain": "Multi-modal, multi-task",
  "format": "TF",
  "year": "2026",
  "modalities": "Music in audio, text, and image format",
  "skills": "music theory understanding, sheet music understanding, and performance audio analysis (performance evaluation: key accuracy, completeness; consistency evaluation: tempo stability, speed)",
  "sources": "public domain (older archive sources) or provided directly by performers under Creative Commons licenses  (precise origin undisclosed)",
  "size": "513 recordings",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "http://arxiv.org/abs/2601.11968"
   }
  ],
  "paper_url": "http://arxiv.org/abs/2601.11968",
  "hf_url": "",
  "code_url": "",
  "bibtex": "@online{zhaoMuseAgent1InteractiveGrounded2026a,\n  title = {{{MuseAgent-1}}: {{Interactive Grounded Multimodal Understanding}} of {{Music Scores}} and {{Performance Audio}}},\n  shorttitle = {{{MuseAgent-1}}},\n  author = {Zhao, Qihao and Cao, Yunqi and Huang, Yangyu and Leong, Hui Yi and Zhang, Fan and Yap, Kim-Hui and Hu, Wei},\n  date = {2026-01-17},\n  eprint = {2601.11968},\n  eprinttype = {arXiv},\n  eprintclass = {cs.MM},\n  doi = {10.48550/arXiv.2601.11968},\n  url = {http://arxiv.org/abs/2601.11968},\n  pubstate = {prepublished},\n}",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "PARSA-Bench",
  "extended": "Persian Audio Reasoning and Speech Assessment Benchmark",
  "paper_title": "PARSA-Bench: A Comprehensive Persian Audio-Language Model Benchmark",
  "domain": "Multi-task",
  "format": "",
  "year": "2026",
  "modalities": "Speech / Music / Audio",
  "skills": "Speech understanding, paralinguistic analysis, Persian cultural audio understanding",
  "sources": "Common Voice, ParsVoice, CoVoST2, MASSIVE, Mana-TTS, YouTube, ParsiNLU, TinyStories, SHEMO, Ganjoor, Persian Music Dataset",
  "size": "8,000 samples",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2603.14456"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/MohammadJRanjbar/PARSA-Bench"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2603.14456",
  "hf_url": "https://huggingface.co/datasets/MohammadJRanjbar/PARSA-Bench",
  "code_url": "",
  "bibtex": "@misc{kalahroodi2026parsabenchcomprehensivepersianaudiolanguage,\n      title={PARSA-Bench: A Comprehensive Persian Audio-Language Model Benchmark}, \n      author={Mohammad Javad Ranjbar Kalahroodi and Mohammad Amini and Parmis Bathayan and Heshaam Faili and Azadeh Shakery},\n      year={2026},\n      eprint={2603.14456},\n      archivePrefix={arXiv},\n      primaryClass={cs.CL},\n      url={https://arxiv.org/abs/2603.14456}, \n}",
  "status": "confirmed",
  "question_count": 0,
  "has_questions": false,
  "questions_url": ""
 },
 {
  "name": "PitchBench",
  "extended": "/",
  "paper_title": "PitchBench: Measuring Pitch Hearing in Audio-Language Models",
  "domain": "Diagnostic / Focused",
  "format": "OEQ",
  "year": "2026",
  "modalities": "Audio / Music",
  "skills": "Absolute and relative pitch perception across 3 levels (atomic, contextual, and melodic), 28 experiments across 6 categories",
  "sources": "Synthetic stimuli (FluidSynth), Bach 4-part chorales (music21), Acoustic processing (Pedalboard)",
  "size": "17,667",
  "models": "",
  "links": [
   {
    "label": "arXiv",
    "url": "https://arxiv.org/abs/2605.26176"
   },
   {
    "label": "Hugging Face",
    "url": "https://huggingface.co/datasets/pitchbench-authors/PitchBench"
   }
  ],
  "paper_url": "https://arxiv.org/abs/2605.26176",
  "hf_url": "https://huggingface.co/datasets/pitchbench-authors/PitchBench",
  "code_url": "",
  "bibtex": "@misc{dujardinPitchBenchMeasuringPitch2026,\n  title = {{{PitchBench}}: {{Measuring Pitch Hearing}} in {{Audio-Language Models}}},\n  shorttitle = {{{PitchBench}}},\n  author = {Dujardin, Milan Liessens and Yu, Song-Ze and {Thomas-Smith}, Craver Corbyn and Chan, David M. and Nguyen, Karina},\n  year = 2026,\n  month = may,\n  number = {arXiv:2605.26176},\n  eprint = {2605.26176},\n  primaryclass = {cs.SD},\n  publisher = {arXiv},\n  doi = {10.48550/arXiv.2605.26176},\n  archiveprefix = {arXiv},\n}",
  "status": "confirmed",
  "question_count": 15648,
  "has_questions": true,
  "questions_url": "data/questions/pitchbench.json"
 }
]

"""Glossário (definido pelo user e/ou padrão + IA)."""

from __future__ import annotations

import csv
from pathlib import Path


# Glossário (Termos padrão; EG e PT)
PADRAO: dict[str, str] = {
    "roasting": "torra", "roasting degree": "grau de torra", "roast degree": "grau de torra", "roasting process": "processo de torra",
    "fermentation": "fermentação", "anaerobic fermentation": "fermentação anaeróbia", "self-induced anaerobic fermentation": "fermentação anaeróbia autoinduzida",
    "solid-state fermentation": "fermentação em estado sólido", "carbonic maceration": "maceração carbônica", "spontaneous fermentation": "fermentação espontânea",
    "starter culture": "cultura iniciadora", "starter cultures": "culturas iniciadoras", "yeast": "levedura", "yeasts": "leveduras", "inoculation": "inoculação",
    "lactic acid bacteria": "bactérias ácido-láticas", "microbial community": "comunidade microbiana", "microorganisms": "micro-organismos", "microbiota": "microbiota",
    "post-harvest processing": "processamento pós-colheita", "postharvest": "pós-colheita", "post-harvest": "pós-colheita", "primary processing": "processamento primário",
    "processing": "processamento", "processing method": "método de processamento", "processing methods": "métodos de processamento",
    "wet processing": "processamento via úmida", "dry processing": "processamento via seca", "natural process": "processo natural", "honey process": "processo cereja descascado",
    "drying": "secagem", "freeze-drying": "liofilização", "spray-drying": "secagem por atomização", "spray drying": "secagem por atomização", "germination": "germinação",
    "storage": "armazenamento", "aging": "envelhecimento", "accelerated aging": "envelhecimento acelerado", "decaffeination": "descafeinação", "malting": "malteação",
    "brewing": "preparo da bebida", "brewing method": "método de preparo", "brewing methods": "métodos de preparo", "extraction": "extração", "extraction method": "método de extração",
    "extraction methods": "métodos de extração", "cold brew": "cold brew", "cold brew coffee": "café cold brew", "hot brew": "preparo a quente", "espresso": "espresso",
    "espresso coffee": "café espresso", "pour-over": "coado (pour-over)", "filter coffee": "café filtrado", "capsules": "cápsulas", "coffee capsules": "cápsulas de café",
    "encapsulation": "encapsulamento", "microencapsulation": "microencapsulação", "ultrasound": "ultrassom", "high pressure processing": "alta pressão", "thermal processing": "processamento térmico",
    "heat treatment": "tratamento térmico", "enzymatic treatment": "tratamento enzimático", "asparaginase": "asparaginase", "concentration": "concentração",
    "coffee": "café", "green coffee": "café verde", "green coffee beans": "grãos de café verde", "green beans": "grãos verdes", "roasted coffee": "café torrado",
    "coffee beans": "grãos de café", "specialty coffee": "café especial", "specialty coffees": "cafés especiais", "arabica": "arábica", "coffea arabica": "Coffea arabica",
    "robusta": "robusta", "coffea canephora": "Coffea canephora", "conilon": "conilon", "civet coffee": "café de civeta", "kopi luwak": "kopi luwak",
    "coffee leaves": "folhas de café", "coffee leaf": "folha de café", "coffee pulp": "polpa de café", "coffee husk": "casca de café", "coffee by-products": "subprodutos do café",
    "by-products": "subprodutos", "spent coffee grounds": "borra de café", "coffee oil": "óleo de café", "coffee brew": "bebida de café", "coffee beverage": "bebida de café",
    "beverage": "bebida", "beverages": "bebidas", "tea": "chá", "black tea": "chá preto", "date seeds": "sementes de tâmara", "date palm": "tamareira", "cocoa": "cacau",
    "instant coffee": "café solúvel", "soluble coffee": "café solúvel", "cultivar": "cultivar", "cultivars": "cultivares", "variety": "variedade", "varieties": "variedades",
    "volatile compounds": "compostos voláteis", "volatile compound": "compostos voláteis", "volatiles": "compostos voláteis", "volatile organic compounds": "compostos orgânicos voláteis",
    "volatile profile": "perfil de voláteis", "volatile profiles": "perfis de voláteis", "volatilome": "voloma", "aroma compounds": "compostos de aroma",
    "aroma-active compounds": "compostos odoríferos ativos", "odorants": "odorantes", "key odorants": "odorantes-chave", "flavor compounds": "compostos de sabor",
    "non-volatile compounds": "compostos não voláteis", "aroma precursors": "precursores de aroma", "flavor precursors": "precursores de sabor", "metabolites": "metabólitos",
    "pyrazines": "pirazinas", "pyrazine": "pirazinas", "furans": "furanos", "furan": "furanos", "aldehydes": "aldeídos", "ketones": "cetonas", "esters": "ésteres",
    "alcohols": "álcoois", "phenols": "fenóis", "phenolic compounds": "compostos fenólicos", "pyrroles": "pirróis", "pyridines": "piridinas", "terpenes": "terpenos",
    "terpenoids": "terpenoides", "sulfur compounds": "compostos sulfurados", "organosulfur compounds": "compostos organossulfurados", "thiols": "tióis", "acids": "ácidos",
    "organic acids": "ácidos orgânicos", "chlorogenic acids": "ácidos clorogênicos", "chlorogenic acid": "ácido clorogênico", "caffeic acid": "ácido cafeico",
    "quinic acid": "ácido quínico", "caffeine": "cafeína", "trigonelline": "trigonelina", "acrylamide": "acrilamida", "melanoidins": "melanoidinas", "sugars": "açúcares",
    "sucrose": "sacarose", "carbohydrates": "carboidratos", "amino acids": "aminoácidos", "free amino acids": "aminoácidos livres", "lipids": "lipídios", "fatty acids": "ácidos graxos",
    "proteins": "proteínas", "glycosides": "glicosídeos", "linalool": "linalol", "maillard reaction": "reação de Maillard", "strecker degradation": "degradação de Strecker",
    "lipid oxidation": "oxidação lipídica", "antioxidant activity": "atividade antioxidante", "bioactive compounds": "compostos bioativos", "chemical composition": "composição química",
    "biomarkers": "biomarcadores", "markers": "marcadores", "chemical markers": "marcadores químicos", "quality markers": "marcadores de qualidade",
    "aroma": "aroma", "flavor": "sabor", "flavour": "sabor", "taste": "gosto", "odor": "odor", "odour": "odor", "aroma profile": "perfil aromático",
    "flavor profile": "perfil de sabor", "sensory": "análise sensorial", "sensory analysis": "análise sensorial", "sensory evaluation": "avaliação sensorial",
    "sensory attributes": "atributos sensoriais", "sensory profile": "perfil sensorial", "sensory quality": "qualidade sensorial", "sensory properties": "propriedades sensoriais",
    "cup quality": "qualidade de bebida", "coffee quality": "qualidade do café", "quality": "qualidade", "quality control": "controle de qualidade", "cupping": "prova de xícara",
    "consumer acceptance": "aceitação pelo consumidor", "consumer": "consumidor", "acceptability": "aceitabilidade", "bitterness": "amargor", "acidity": "acidez",
    "sweetness": "doçura", "astringency": "adstringência", "fruity": "frutado", "off-flavor": "defeito sensorial", "off-flavors": "defeitos sensoriais", "defects": "defeitos",
    "potato taste defect": "defeito de gosto de batata", "umami": "umami",
    "geographical origin": "origem geográfica", "geographic origin": "origem geográfica", "origin": "origem", "altitude": "altitude", "terroir": "terroir",
    "authentication": "autenticação", "authenticity": "autenticidade", "adulteration": "adulteração", "traceability": "rastreabilidade", "discrimination": "discriminação",
    "classification": "classificação", "fingerprinting": "impressão digital química", "chemical fingerprinting": "impressão digital química", "climate": "clima", "temperature": "temperatura",
    "metabolomics": "metabolômica", "untargeted metabolomics": "metabolômica não direcionada", "metabolomic profiling": "perfil metabolômico", "metabolite profiling": "perfil de metabólitos",
    "metagenomics": "metagenômica", "multi-omics": "multiômica", "chemometrics": "quimiometria", "machine learning": "aprendizado de máquina", "artificial intelligence": "inteligência artificial",
    "electronic nose": "nariz eletrônico", "e-nose": "nariz eletrônico", "electronic tongue": "língua eletrônica", "e-tongue": "língua eletrônica", "gas chromatography": "cromatografia gasosa",
    "mass spectrometry": "espectrometria de massas", "gas chromatography-mass spectrometry": "cromatografia gasosa–espectrometria de massas", "olfactometry": "olfatometria",
    "ion mobility spectrometry": "espectrometria de mobilidade iônica", "solid-phase microextraction": "microextração em fase sólida", "headspace": "headspace",
    "principal component analysis": "análise de componentes principais", "multivariate analysis": "análise multivariada", "correlation analysis": "análise de correlação",
    "odor activity value": "valor de atividade odorífera", "odour activity value": "valor de atividade odorífera", "kinetics": "cinética", "dynamic changes": "mudanças dinâmicas",
    "health": "saúde", "human intervention": "intervenção em humanos", "urine": "urina", "bioavailability": "biodisponibilidade", "blood-brain barrier": "barreira hematoencefálica",
    "indoor air quality": "qualidade do ar interior", "edible insects": "insetos comestíveis", "insect oils": "óleos de insetos", "cigar": "charuto", "black pepper": "pimenta-do-reino",
    "chicory": "chicória", "chaya": "chaya", "valorization": "valorização",
    "fruit": "notas de frutas", "fruits": "notas de frutas", "antioxidant": "atividade antioxidante", "antioxidants": "antioxidantes",
    "bitter": "amargor", "sweet": "doçura", "sour": "acidez", "body": "corpo", "aftertaste": "retrogosto", "fragrance": "fragrância",
    "green coffee bean": "grãos de café verde", "volatile composition": "composição volátil", "key aroma compounds": "compostos-chave de aroma",
    "odor-active compounds": "compostos odoríferos ativos", "aroma release": "liberação de aroma", "shelf life": "vida de prateleira",
    "lactic acid": "ácido lático", "acetic acid": "ácido acético", "ethanol": "etanol", "glycerol": "glicerol", "mannitol": "manitol",
    "polyphenols": "polifenóis", "flavonoids": "flavonoides", "alkaloids": "alcaloides", "nucleotides": "nucleotídeos",
    "peptides": "peptídeos", "biogenic amines": "aminas biogênicas", "minerals": "minerais", "tocopherols": "tocoferóis",
    "sterols": "esteróis", "triacylglycerols": "triacilgliceróis", "diterpenes": "diterpenos", "lactones": "lactonas",
    "furanones": "furanonas", "pyrazine compounds": "pirazinas", "guaiacol": "guaiacol", "2-furfurylthiol": "2-furfuriltiol",
    "furfural": "furfural", "hexanal": "hexanal", "acetaldehyde": "acetaldeído", "diacetyl": "diacetil",
    "glucose": "glicose", "fructose": "frutose", "mannose": "manose", "galactose": "galactose", "arabinose": "arabinose",
    "monosaccharides": "monossacarídeos", "polysaccharides": "polissacarídeos", "citric acid": "ácido cítrico", "malic acid": "ácido málico",
    "succinic acid": "ácido succínico", "quinic acid lactones": "lactonas do ácido quínico", "asparagine": "asparagina",
    "phenylalanine": "fenilalanina", "glutamic acid": "ácido glutâmico", "theobromine": "teobromina",
}


# Termos Excluídos
VAGOS = {
    "process", "processes", "profile", "profiles", "compound", "compounds", "method", "methods", "analysis", "technique",
    "techniques", "approach", "sample", "samples", "treatment", "treatments", "result", "results", "study", "data", "model",
    "models", "level", "levels", "content", "contents", "concentration", "aromatic", "hot", "cold", "high", "low", "volatile",
    "volatile organic", "condition", "conditions", "effect", "effects", "change", "changes", "characteristic", "characteristics",
    "property", "properties", "component", "components", "difference", "differences", "type", "types", "group", "groups",
    "performance", "accuracy", "value", "values", "factor", "factors", "parameter", "parameters", "variable", "variables",
    "time", "times", "period", "stage", "stages", "condition", "number", "rate", "ratio", "score", "scores", "intensity",
    "increase", "increases", "decrease", "decreases", "day", "days", "week", "weeks", "year", "years", "month", "months",
    "use", "used", "using", "evidence", "impact", "role", "case", "cases", "review", "approach", "development", "analysis of",
    "uso", "usos", "efeito", "efeitos", "estudo", "estudos", "dados", "resultado", "resultados", "análise", "método", "métodos",
    "dia", "dias", "ano", "anos", "mês", "meses", "avaliação", "desempenho", "relação", "fatores", "fator", "impacto",
    "estudio", "estudios", "efecto", "efectos", "datos", "resultado", "análisis", "método", "métodos", "uso",
}

METODOLOGICOS = VAGOS | {
    "correlation analysis", "principal component analysis", "multivariate analysis", "chemometrics", "chemometric", "mass spectrometry",
    "gas chromatography", "gas chromatography-mass spectrometry", "headspace", "solid-phase microextraction", "olfactometry",
    "ion mobility spectrometry", "electronic nose", "e-nose", "electronic tongue", "e-tongue", "machine learning", "metabolomics",
    "untargeted metabolomics", "metabolomic profiling", "metabolite profiling", "statistical analysis",
    "gc-ms", "gc–ms", "hs-spme", "gc-ims", "lc-ms", "uplc-ms", "gc-o", "gc×gc", "spme", "pca", "pls-da", "opls-da", "anova",
}

GENERICOS = {
    "article", "human", "humans", "nonhuman", "controlled study", "chemistry", "priority journal", "procedures", "metabolism", "analysis", "coffee", "coffea",
    "food", "foods", "beverage", "beverages", "female", "male", "adult", "animal", "animals", "unclassified drug", "drug effect", "comparative study", "plant seed",
    "seed", "seeds", "plant", "plants", "food analysis", "food handling", "food quality", "food processing", "quality", "chemical analysis", "concentration (parameter)",
    "concentration (composition)", "molecular weight", "mass spectrometry", "gas chromatography", "gas chromatography-mass spectrometry", "gas chromatography mass spectrometry",
    "chromatography", "spectrometry", "principal component analysis", "multivariate analysis", "statistics", "statistical analysis", "procedure", "methodology", "method",
    "methods", "comparison", "evaluation", "temperature", "taste", "odor", "odour", "aroma", "flavor", "flavour", "sensory", "volatile organic compounds",
    "volatile organic compound", "volatile compounds", "volatile compound", "volatiles", "chemical composition", "controlled study", "nonhuman", "drinking", "drink",
    "china", "brazil", "colombia", "indonesia", "ethiopia", "egypt", "kenya", "yunnan", "vietnam", "mexico", "peru", "italy", "spain", "portugal", "korea", "japan",
    "chemical compounds", "organic compounds", "solid phase microextraction", "solid-phase microextraction", "headspace analysis", "extraction", "sensory analysis",
    "sensory evaluation", "smelling", "perception", "volatilization", "chemometrics", "metabolomics", "flavor compounds", "aroma compounds",
}


# Glossário do user
def carregar(caminho: Path | None) -> dict[str, str]:
    glossario = dict(PADRAO)
    if caminho and caminho.exists():
        with open(caminho, encoding="utf-8-sig", newline="") as f:
            for linha in csv.reader(f, delimiter=";"):
                if len(linha) >= 2 and linha[0].strip() and not linha[0].startswith("#"):
                    glossario[linha[0].strip().lower()] = linha[1].strip()
    return glossario

# coding: utf-8

import os, sys
import rdflib, requests
from rdflib import Graph, Namespace, URIRef, Literal, OWL
from SPARQLWrapper import SPARQLWrapper, JSON
import time
 # TODO: lexvo lookup

base_uri = 'http://lexbib.org/data/id/'

def construct_value_statement(urls):
    value_statement = "VALUES(?wikidataurl) {"
    value_statement = value_statement + " ".join(["(\"%s\")" % url
        for url in urls])
    value_statement = value_statement + "}"
    return value_statement

def get_descriptions(wiki_data_urls):
    descs = []
    for link in wiki_data_urls:
        wikidata_query = f"""
PREFIX wd: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX schema: <http://schema.org/>
SELECT DISTINCT ?entity_label ?instance_label ?desc 
WHERE {{
  <{link}> wd:P31 ?instance.
  OPTIONAL {{
    <{link}> schema:description ?desc.
    FILTER (lang(?desc) = "en" || lang(?desc) = "")
    }}.
  ?instance rdfs:label ?instance_label.
  <{link}> rdfs:label ?entity_label.
  FILTER (lang(?entity_label) = "en" || lang(?entity_label) = "")
  FILTER (lang(?instance_label) = "en" || lang(?instance_label) = "")
}}
"""
        sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
        sparql.setQuery(wikidata_query)
        sparql.setReturnFormat(JSON)
        result = sparql.query().convert()["results"]["bindings"][0]
        desc_dict = {key : result[key]["value"] for key in ["instance_label", "entity_label", "desc"] if key in result.keys()}
        desc_dict["url"] = link
        descs.append(desc_dict)
    return descs


def display_possibilities(name, value_list):
    print("Possibilities for %s" % name)
    for i in range(len(value_list)):
        item_dict = value_list[i]
        dict_rep = [("%s: %s" % (key, value)) for key, value in item_dict.items()]
        rep = "[%s] %s" % (i, ", ".join(dict_rep))
        print(rep)
        

def get_preferedAnswer(value_list):
    falseAnswer = True
    while falseAnswer:
        index = input("Give me an index, X for abort: ")
        if index == "X":
            return None
        else:
            try:
                i = int(index)
            except ValueError:
                continue
            if len(value_list)>i:
                return value_list[i]

def figure_out_correct_link(name): 
    wikidata_lookup = f"""
PREFIX wd: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?x
WHERE {{ 
    VALUES(?label) {{
       ( "{name}" )
       ( "{name}"@en )
       ( "{name}"@de )
      }}
    ?x ?p ?label
     ; wd:P31/wd:P279* <http://www.wikidata.org/entity/Q43229>
}}
"""
    sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
    sparql.setQuery(wikidata_lookup)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()["results"]["bindings"]
    if len(results)>1:
        descs = get_descriptions([result["x"]["value"] for result in results])
        display_possibilities(name, descs)
        result = get_preferedAnswer(descs)
        if result == None:
            return backup_babelfy(name)
        return result["url"]
    if len(results)==0:
        return backup_babelfy(name)

def backup_babelfy(name):
    payload = {'key': 'KEY', 'text': name}
    req = "http://babelfy.io/v1/disambiguate" 
    resp = requests.get(req, params=payload)
    try :
        dburl = resp.json()[0]["DBpediaURL"]
    except KeyError:
        return None
    dbpedia = SPARQLWrapper('https://dbpedia.org/sparql')
    dbquery = f"""
    PREFIX owl: <http://www.w3.org/2002/07/owl#> 
    SELECT DISTINCT ?same WHERE{{
        <{str(dburl)}> a <http://dbpedia.org/ontology/Organisation>; owl:sameAs ?same 
        FILTER (STRSTARTS(str(?same), "http://www.wikidata.org/entity/"))
    }}
    """
    dbpedia.setQuery(dbquery)
    dbpedia.setReturnFormat(JSON)
    results = dbpedia.query().convert()
    res = results['results']['bindings']
    if len(res) > 0 :
        print(res[0]['same']['value'])
        return res[0]['same']['value']
    

def make_uri(name, typ):
	name_sane = name.lower().replace('/','--').strip().replace(' ','_')
	return base_uri + typ + '/' + name_sane

def reconcile_publisher(name, targetGraph):
    pub_uri = make_uri(name, 'organization')

    qupd = f"""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{ ?x dct:publisher ?pub . ?pub foaf:name "{name}" ; ?p ?y }}
INSERT {{ ?x dct:publisher <{pub_uri}> . <{pub_uri}> foaf:name "{name}" ; ?p ?y }}
WHERE {{ 
    ?x dct:publisher ?pub . ?pub foaf:name "{name}" ; ?p ?y
}}
"""
    res = targetGraph.update(qupd)
    final_uri = figure_out_correct_link(name)
    # if nothing works, just make up your own
    final_uri = "%s%s" % (base_uri, name.replace(" ","_")) if final_uri == None else final_uri
    print("Final URI: %s" % final_uri)
    targetGraph.add( ( URIRef(pub_uri), OWL.sameAs, URIRef(final_uri) ) )
    return targetGraph

# TODO missuse foaf:sthname
# TODO locality hasSite

## Main program
file = sys.argv[1]
g = Graph()
g.parse(file)
q = """
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
SELECT DISTINCT ?p ?name WHERE { 
 [] dct:publisher ?p . ?p foaf:name ?name
}"""
res = g.query(q)
names = set(row[1] for row in res)
for name in names:
   reconcile_publisher(name, g)

with open("lexvo-iso639-1-mapping.tsv", "r", encoding="utf-8") as f:
    lexvo_mapping = {}
    for line in f:
        key, value = line.strip().split("\t")
        # value = value.split("/")[-1]
        lexvo_mapping[key] = value
language_query = """
PREFIX dcterms: <http://purl.org/dc/terms/> 
SELECT ?paper_id ?lang WHERE {
    ?paper_id dcterms:language ?lang;
}
"""
res = g.query(language_query)
print(len(res))
# for paper_id, lang in res:
#     lang = str(lang)
#     print("%s, old: %s, new: %s" % (paper_id, lang, lexvo_mapping[lang]))
language_fix = f"""
PREFIX lexvo: <http://lexvo.org/id/iso639-3/>
PREFIX dcterms: <http://purl.org/dc/terms/>
DELETE {{
    ?paper_id dcterms:language ?lang .
}}
INSERT {{
    ?paper_id dcterms:language ?new_lang .
}}
WHERE {{
    VALUES (?lang ?new_lang) {{
        {" ".join(["('%s' <%s>) " % (key, value) for key, value in lexvo_mapping.items()])}
        {" ".join(["('%s' <%s>) " % (key.upper(), value) for key, value in lexvo_mapping.items()])}
    }}
    ?paper_id dcterms:language ?lang .
}}
"""

g.update(language_fix)


fix_blank_authorlists = f"""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{
    ?x bibo:authorList ?blank .
    ?blank ?p_2 ?o_2 .
}}
INSERT {{
    ?x bibo:authorList ?authorlistnew .
    ?authorlistnew ?p_2 ?o_2 .
}}
WHERE {{
    ?x bibo:authorList ?blank .
    ?blank ?p_2 ?o_2 .
    BIND(URI(CONCAT(STR(?x),"#authorList")) as ?authorlistnew)
}}
"""
print(fix_blank_authorlists)
g.update(fix_blank_authorlists)


simple_authorfix = f"""
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{
    ?author_old a foaf:Person; foaf:givenname ?f ; foaf:surname ?s .
    ?sth ?p ?author_old .
}}
INSERT {{
    ?author_new a foaf:Person; foaf:givenname ?f ; foaf:surname ?s .
    ?sth ?p ?author_new .
}}
WHERE {{
    ?author_old a foaf:Person; foaf:givenname ?f ; foaf:surname ?s .
    ?sth ?p ?author_old .
    BIND(URI(
        REPLACE(
        REPLACE(
            CONCAT("{base_uri}",
                    LCASE(STR(?f))
                    ,"_",
                    LCASE(STR(?s))
                )
            ," ","_")
        ,"\\\\.","") 
        )
    as ?author_new)
}}
"""

print(simple_authorfix)
g.update(simple_authorfix)



fix_blank_editorlists = f"""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{
    ?x bibo:editorList ?blank .
    ?blank ?p_2 ?o_2 .
}}
INSERT {{
    ?x bibo:editorList ?editorlistnew .
    ?editorlistnew ?p_2 ?o_2 .
}}
WHERE {{
    ?x bibo:editorList ?blank .
    ?blank ?p_2 ?o_2 .
    BIND(URI(CONCAT(STR(?x),"#editorList")) as ?editorlistnew)
}}
"""
#print(fix_blank_editorlists)
#g.update(fix_blank_editorlists)
q = f"""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{
    # fixing authors
    ?x dct:creator ?a .
    ?a a foaf:Person ; foaf:givenname ?f ; foaf:surname ?s .
    ?x1 ?p1 ?a .

    # fixing author lists
    ?x bibo:authorList ?authorlist .
    ?authorlist ?p_author ?o_author .
    ?authorlist a ?tseq .
}}
INSERT {{
    # fixing authors
    ?x dct:creator ?authoruri .
    ?authoruri a foaf:Person ; foaf:givenname ?f ; foaf:surname ?s .
    ?x1 ?p1 ?authoruri .
    
    # fixing author lists
    ?x bibo:authorList ?authorlistnew .
    ?authorlistnew ?p_author ?authoruri .
    ?authorlistnew a ?tseq .
}}
WHERE {{
    # fixing authors
    ?x dct:creator ?a .
    ?a a foaf:Person ; foaf:givenname ?f ; foaf:surname ?s .
    ?x1 ?p1 ?a.

    # fixing author lists
    ?x bibo:authorList ?authorlist .
    ?authorlist ?p_author ?o_author .
    FILTER STRSTARTS(STR(?p_author), "http://www.w3.org/1999/02/22-rdf-syntax-ns#_")
    ?authorlist a ?tseq . 
    BIND(URI(CONCAT(STR(?x),"authorList")) as ?authorlistnew)
    BIND(URI(REPLACE(REPLACE(CONCAT("{base_uri}",LCASE(STR(?s)),"_",LCASE(STR(?f)),"_",LCASE(STR(?f)))," ","_"), ".", "")) as ?authoruri)
    
}}
"""


#print(q)
#res = g.update(q)

q = f"""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{
    # fixing authors
    ?a a foaf:Person ; foaf:givenname ?f ; foaf:surname ?s .
    ?x1 ?p1 ?a .

    # fixing author lists
    ?x bibo:editorList ?editorlist .
    ?editorlist ?p_author ?o_author .
    ?editorlist a ?tseq .
}}
INSERT {{
    # fixing authors
    ?editoruri a foaf:Person ; foaf:givenname ?f ; foaf:surname ?s .
    ?x1 ?p1 ?editoruri .
    
    # fixing author lists
    ?x bibo:editorList ?editorlistnew .
    ?editorlistnew ?p_author ?editoruri .
    ?editorlistnew a ?tseq .
}}
WHERE {{
    # fixing authors
    ?a a foaf:Person ; foaf:givenname ?f ; foaf:surname ?s .
    ?x1 ?p1 ?a.
    # fixing author lists
    ?paperuri a bibo:Article .
    ?x bibo:editorList ?editorlist .
    ?editorlist ?p_author ?o_author .
    FILTER STRSTARTS(STR(?p_author), "http://www.w3.org/1999/02/22-rdf-syntax-ns#_")
    ?editorlist a ?tseq . 
    BIND(URI(CONCAT(STR(?paperuri),"editorList")) as ?editorlistnew)
    BIND(URI(REPLACE(REPLACE(CONCAT("{base_uri}/creators/",LCASE(STR(?s)),"_",LCASE(STR(?f)))," ","_"), ".", "")) as ?editoruri)
    
}}
"""

#print(q)
# g.update(q)


fix_proceedings = f"""
PREFIX bibo: <http://purl.org/ontology/bibo/>
DELETE {{
    ?proceedings a bibo:Proceedings .
    ?proceedings ?p ?o .
    ?s_2 ?p_2 ?proceedings .
}}
INSERT {{
    ?proceedings_new a bibo:Proceedings .
    ?proceedings_new ?p ?o .
    ?s_2 ?p_2 ?proceedings_new .
}}
WHERE {{
    ?proceedings bibo:isbn13 ?isbn .
    ?proceedings ?p ?o .
    ?s_2 ?p_2 ?proceedings .
    BIND(URI(CONCAT("{base_uri}",LCASE(STR(?isbn)))) as ?proceedings_new)
}}
"""
# print(fix_proceedings)
# g.update(fix_proceedings)

q = f"""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{
    ?s foaf:givenname ?g.
}}
INSERT {{
    ?s foaf:givenName ?g.
}}
WHERE {{
    ?s foaf:givenName ?g.
}}
"""
# g.update(q)
g.namespace_manager.bind('owl', OWL)
dir = 'out'
if not os.path.exists(dir):
    os.makedirs(dir)
# Note: it will overwrite the existing Turtle file!
path = os.path.join(dir, 'zotero.ttl')
g.serialize(destination=path, format='turtle')
print('DONE. ' + str(len(g)) + ' triples written to ' + path)

# coding: utf-8

import os
import rdflib
from rdflib import Graph, Namespace, URIRef, Literal, OWL
from SPARQLWrapper import SPARQLWrapper, JSON

base_uri = 'http://lexbib.org/data/id/'

def make_uri(name, type):
	name_sane = name.lower().replace('/','--').strip().replace(' ','_')
	return base_uri + type + '/' + name_sane

def reconcile_publisher(name, targetGraph):
    pub_uri = make_uri(name, 'organization')

    qupd = f"""
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
DELETE {{ ?x dct:publisher ?pub . ?pub foaf:name ?name ; ?p ?y }}
INSERT {{ ?x dct:publisher <{pub_uri}> . <{pub_uri}> foaf:name ?name ; ?p ?y }}
WHERE {{ 
 ?x dct:publisher ?pub . ?pub foaf:name ?name ; ?p ?y
}}
"""
    res = targetGraph.update(qupd)

    qlookup = f"""
PREFIX wd: <http://www.wikidata.org/prop/direct/>
SELECT DISTINCT ?x
WHERE {{ 
    VALUES(?label) {{
       ( "{name}" )
       ( "{name}"@en )
       ( "{name}"@de )
      }}
    ?x ?p ?label
     ; wd:P31/wd:P279* <http://www.wikidata.org/entity/Q31855>
}}
"""
    sparql = SPARQLWrapper('https://query.wikidata.org/sparql')
    sparql.setQuery(qlookup)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    res = results['results']['bindings']
    if len(res) > 0 :
        targetGraph.add( ( URIRef(pub_uri), OWL.sameAs, URIRef(res[0]['x']['value']) ) )
    return targetGraph


## Main program
file = 'Heid_2014_example_paper.rdf'
g = Graph()
g.parse(file)
q = """
PREFIX dct: <http://purl.org/dc/terms/>
PREFIX foaf: <http://xmlns.com/foaf/0.1/>
SELECT DISTINCT ?p ?name WHERE { 
 [] dct:publisher ?p . ?p foaf:name ?name
}"""
res = g.query(q)
for row in res:
    name = row[1]
    reconcile_publisher(name, g)
    

g.namespace_manager.bind('owl', OWL)
dir = 'out'
if not os.path.exists(dir):
    os.makedirs(dir)
# Note: it will overwrite the existing Turtle file!
path = os.path.join(dir, 'zotero.ttl')
g.serialize(destination=path, format='turtle')
print('DONE. ' + str(len(g)) + ' triples written to ' + path)

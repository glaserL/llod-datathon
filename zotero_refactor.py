# coding: utf-8

import os, sys
from rdflib import Graph, OWL
from linkers import OrganizationLinker


def fix_blank_author_nodes(graph: Graph, uri):
    statement = f"""
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
                CONCAT("{uri}",
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
    graph.update(statement)


def load_lexvo_mapping(path):
    """
    loads a custom mapping from two letter language codes to full lexvo urls.
    :param path:
    :return:
    """
    mapping = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            key, value = line.strip().split("\t")
            mapping[key] = value
    return mapping


def link_language_to_lexvo(g, path_to_mapping):
    lexvo_mapping = load_lexvo_mapping(path_to_mapping)
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


def perform_update_from_file(graph: Graph, path):
    with open(path, encoding="utf-8") as f:
        statement = f.read()
        graph.update(statement)


# Main program
file = sys.argv[1]
base_uri = sys.argv[2] if len(sys.argv) > 2 else 'http://lexbib.org/data/id/'

g = Graph()
g.parse(file)

ol = OrganizationLinker(g, base_uri)
ol.reconcile()

link_language_to_lexvo(g, "lexvo-iso639-1-mapping.tsv")

perform_update_from_file(g, "sparql/fix_blank_authorlists.sparql")

fix_blank_author_nodes(g, base_uri)

perform_update_from_file(g, "sparql/fix_blank_editorlists.sparql")

perform_update_from_file(g, "sparql/fix_givenname_typo.sparql")

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

res = g.update(q)

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

g.update(q)

# TODO: this introuces doubled entries
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


g.namespace_manager.bind('owl', OWL)
dir = 'out'
if not os.path.exists(dir):
    os.makedirs(dir)

# Note: it will overwrite the existing Turtle file!
path = sys.argv[3] if len(sys.argv) > 3 else os.path.join(dir, 'zotero.ttl')
g.serialize(destination=path, format='ttl')
print('DONE. ' + str(len(g)) + ' triples written to ' + path)

# Lectura de los avisos de seguridad de WatchGuard (https://psirt.watchguard.com/).
# De la tabla de avisos se obtiene, para Fireware OS:
#  - la última versión publicada de cada rama (la versión "no afectada" más alta de cada aviso),
#  - qué avisos afectan a cada versión instalada y con qué gravedad.

import functools 
import html as htmllib 
import re 
import urllib .request 
from urllib .parse import urljoin ,urlparse 

PSIRT_URL ="https://psirt.watchguard.com/"
SEVERITIES =["informational","low","medium","high","critical"]
TIMEOUT =20 


def _parse_version (v ):
# Se ignoran sufijos de build: "11.12.4+541730", "12.10.4-b701004", "12.12.2.B745592".
    s =re .sub (r"[+-].*|\.B\d+$","",str (v or ""),count =1 ,flags =re .I )
    return [int (n )for n in re .findall (r"\d+",s )]


def compare_versions (a ,b ):
    pa ,pb =_parse_version (a ),_parse_version (b )
    for i in range (max (len (pa ),len (pb ))):
        d =(pa [i ]if i <len (pa )else 0 )-(pb [i ]if i <len (pb )else 0 )
        if d :
            return d 
    return 0 


version_key =functools .cmp_to_key (compare_versions )


def major (v ):
    m =re .search (r"\d+",str (v or ""))
    return int (m .group ())if m else 0 


def is_t15 (model ):
    return bool (re .match (r"T(15|35)\b",model or "",re .I ))


def branch_of (model ,version ):
    """Rama de firmware de un equipo: los T15/T35 con 12.x tienen una línea 12.5.x propia,
    el resto se separa entre la rama 12.x y las versiones nuevas (2025.x y siguientes)."""
    if major (version )>=2025 :
        return "actual"
    return "T15/T35"if is_t15 (model )else "12.x"


def _strip_tags (s ):
    return htmllib .unescape (re .sub (r"<[^>]+>","",s )).strip ()


def parse_ranges (text ):
    """">= 2025.1, < 2026.4, >= 12.0, <= 11.12.4+541730" -> [{min, min_inc, max, max_inc}, ...]"""
    ranges =[]
    cur =None 
    for part in text .split (","):
        m =re .match (r"(>=|>|<=|<|=)\s*([\d.]+)",part .strip ())
        if not m :
            continue 
        op ,v =m .groups ()
        if op .startswith (">"):
            if cur :
                ranges .append (cur )
            cur ={"min":v ,"min_inc":op ==">="}
        elif op .startswith ("<"):
            cur =cur or {}
            cur .update (max =v ,max_inc =op =="<=")
            ranges .append (cur )
            cur =None 
        else :
            ranges .append ({"min":v ,"min_inc":True ,"max":v ,"max_inc":True })
    if cur :
        ranges .append (cur )
        # Un rango abierto (">= 11.10.2" sin límite superior) se limita a su propia rama mayor,
        # para que no marque como afectadas las versiones de ramas posteriores. Las versiones
        # 2025+ son una sola rama (el número mayor es el año), así que ahí no se pone tope.
    for r in ranges :
        if r .get ("max")is None and r .get ("min")is not None and major (r ["min"])<2025 :
            r .update (max =str (major (r ["min"])+1 ),max_inc =False )
    return ranges 


def in_ranges (version ,ranges ):
    for r in ranges :
        if r .get ("min")is not None :
            c =compare_versions (version ,r ["min"])
            if c <0 or (c ==0 and not r ["min_inc"]):
                continue 
        if r .get ("max")is not None :
            c =compare_versions (version ,r ["max"])
            if c >0 or (c ==0 and not r ["max_inc"]):
                continue 
        return True 
    return False 


def _safe_url (href ,advisory_id ):
    url =urljoin (PSIRT_URL ,href )
    return url if urlparse (url ).scheme =="https"else urljoin (PSIRT_URL ,f'/{advisory_id }/')


def _search (pattern ,text ,default =""):
    m =re .search (pattern ,text )
    return m .group (1 )if m else default 


def parse_advisories (page ):
    """Extrae de la página de avisos solo los que afectan a Fireware OS."""
    advisories =[]
    parts =re .split (r"<tbody>",page ,flags =re .I )
    body =parts [1 ]if len (parts )>1 else page 
    for row in re .split (r"<tr>",body ,flags =re .I )[1 :]:
        advisory_id =_search (r'class="rec-id">([^<]+)',row ,None )
        if not advisory_id :
            continue 
        href =_search (r'<a href="([^"]+)"',row ,f'/{advisory_id }/')
        sev_title =_search (r'class="sevchip"[^>]*title="([^"]*)"',row )
        severity =next ((s for s in SEVERITIES if s in sev_title .lower ()),"informational")
        score =_search (r"CVSS\s+([\d.]+)",sev_title ,None )
        summary =_strip_tags (_search (r"</span>(.*?)</a>",row ))
        date =_search (r"<time[^>]*>([^<]+)</time>",row )

        # Bloque de producto Fireware OS dentro de la celda de afectados.
        cell =_search (r'class="affcell">(.*?)</td>',row )
        blocks =re .split (r'<div class="prod">|<span class="prodinline">',cell )[1 :]
        fw =next ((b for b in blocks if b .startswith ("Fireware OS")),None )
        if fw is None :
            continue 

        platforms ={}
        plat ="Default"
        for kind ,text in re .findall (r'<span class="(plat|aff|naff)[^"]*">(?:<span class="platchip">)?([^<]*)',fw ):
            value =htmllib .unescape (text ).strip ()
            if kind =="plat":
                plat =value or "Default"
                continue 
            p =platforms .setdefault (plat ,{"affected":[],"not_affected":[]})
            if value and value !="—":
                if kind =="aff":
                    p ["affected"]=parse_ranges (value )
                else :
                    p ["not_affected"]=[r ["min"]for r in parse_ranges (value )if r .get ("min")]
        advisories .append ({
        "id":advisory_id ,
        "url":_safe_url (href ,advisory_id ),
        "severity":severity ,
        "score":score ,
        "summary":summary ,
        "date":date ,
        "platforms":platforms ,
        })
    return advisories 


def _is_125 (v ):
    return bool (re .match (r"12\.5\.",v ))


def latest_by_branch (advisories ):
    """Las versiones "no afectadas" son las versiones que corrigen cada aviso; la más alta de cada
    rama es la última versión publicada que conocemos."""
    latest ={}

    def bump (branch ,v ):
        if branch not in latest or compare_versions (v ,latest [branch ])>0 :
            latest [branch ]=v 

    for a in advisories :
        for v in a ["platforms"].get ("Default",{}).get ("not_affected",[]):
            bump ("actual"if major (v )>=2025 else "12.x",v )
            # Igual que advisories_for: una corrección 12.5.x en la plataforma general vale para T15/T35.
            if _is_125 (v ):
                bump ("T15/T35",v )
        for v in a ["platforms"].get ("T15/T35",{}).get ("not_affected",[]):
            bump ("actual"if major (v )>=2025 else "T15/T35",v )
    return latest 


def _sort_key (a ):
    return (SEVERITIES .index (a ["severity"]),float (a .get ("score")or 0 ))


def advisories_for (advisories ,model ,version ):
    """Avisos que afectan a un equipo concreto, con la versión que lo corrige en su rama."""
    if not version :
        return []
    branch =branch_of (model ,version )

    def same_branch (v ):
        if branch =="T15/T35":
            return _is_125 (v )
        return (major (v )>=2025 )==(branch =="actual")

    out =[]
    for a in advisories :
    # Los T15/T35 con 12.x usan su línea propia; si el aviso no la indica, se usa la general
    # solo cuando tiene una corrección dentro de la línea 12.5.x.
        p =a ["platforms"].get ("Default")
        if branch =="T15/T35":
            p =a ["platforms"].get ("T15/T35")or a ["platforms"].get ("—")
            default =a ["platforms"].get ("Default")
            if not p and default and any (same_branch (v )for v in default ["not_affected"]):
                p =default 
        if not p or not p ["affected"]or not in_ranges (version ,p ["affected"]):
            continue 
        fixes =sorted ((v for v in p ["not_affected"]if compare_versions (v ,version )>0 ),key =version_key )
        fix =next ((v for v in fixes if same_branch (v )),fixes [0 ]if fixes else None )
        out .append ({k :a [k ]for k in ("id","url","severity","score","summary")}|{"fix":fix })
    return sorted (out ,key =_sort_key ,reverse =True )


def fetch_advisories ():
    req =urllib .request .Request (PSIRT_URL ,headers ={"User-Agent":"panel-watchguard/1.0","Accept":"text/html"})
    with urllib .request .urlopen (req ,timeout =TIMEOUT )as res :
        page =res .read ().decode ("utf-8",errors ="replace")
    advisories =parse_advisories (page )
    if not advisories :
        raise RuntimeError ("No se encontraron avisos de Fireware en la página PSIRT (¿cambió el formato?)")
    return advisories 

"""Suspect words: flags only, never corrections.

A word the dictionary does not know is a suspect — an OCR misread ("cight",
"me1ting"), a name, or a word the list lacks. The app shows them so a person
looks; nothing here changes text (decision of 2026-09-09: zero-shot reading,
no word-list correction). A per-library ignore list (dictionary.txt) removes
the names and jargon a person has vouched for.

The engine is pyspellchecker's English list, which is American. British and
Australian spellings are added here: explicit lists for the irregular
families (-our, -re, -ence, -ogue, ae/oe, one-offs) and rules over the
dictionary for the regular ones (-ise/-isation from -ize, -yse from -yze,
doubled l in travelled/modelling). The rules over-generate a few words no one
writes ("sise" from "size"); those only mean a misspelling nobody makes would
go unflagged.

Names: a capitalised word the dictionary lacks but which recurs on several
pages of one document (Fred, NoNo, Kotter) is treated as a name and not
flagged — a book's characters would otherwise be flagged on every page.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass

_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’]*[A-Za-z0-9]|[A-Za-z0-9]")
_HYPHEN_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*[A-Za-z0-9]|[A-Za-z0-9]")

NAME_PAGES = 3  # a capitalised unknown on this many pages is a name, not a suspect


@dataclass(frozen=True)
class Suspect:
    word: str
    start: int  # character offsets into the line's shown text
    end: int

    def to_dict(self) -> dict:
        return {"word": self.word, "start": self.start, "end": self.end}


# --------------------------------------------------------------------------- #
# British and Australian spellings
# --------------------------------------------------------------------------- #
_OUR_STEMS = (
    "arbour ardour armour behaviour candour clamour colour demeanour endeavour favour "
    "fervour flavour glamour harbour honour humour labour misdemeanour neighbour odour "
    "parlour rancour rigour rumour saviour savour splendour succour tumour valour vapour vigour"
).split()
_OUR_SUFFIXES = [
    "",
    "s",
    "ed",
    "ing",
    "ings",
    "er",
    "ers",
    "ful",
    "fully",
    "less",
    "ite",
    "ites",
    "able",
    "ably",
    "ism",
    "hood",
    "al",
    "ally",
]
_EXPLICIT = """
centre centres centred centring metre metres kilometre kilometres millimetre millimetres
centimetre centimetres litre litres millilitre millilitres theatre theatres fibre fibres calibre
sombre spectre lustre sceptre manoeuvre manoeuvres manoeuvred manoeuvring meagre mitre nitre ochre
sabre sabres sepulchre louvre epicentre reconnoitre goitre amphitheatre
defence defences offence offences licence licences pretence pretences
catalogue catalogues catalogued cataloguing dialogue dialogues monologue monologues analogue
analogues epilogue prologue travelogue demagogue synagogue pedagogue ideologue
anaemia anaemic anaesthesia anaesthetic anaesthetist archaeology archaeological encyclopaedia
haemoglobin haemorrhage leukaemia mediaeval orthopaedic paediatric paediatrician aeon aeons
aetiology gynaecology diarrhoea foetus foetal oesophagus oestrogen amoeba homoeopathy faeces caesium
grey greys greyer greyest greying greyish programme programmes tyre tyres kerb kerbs cheque
cheques chequebook mould moulds moulded moulding mouldy plough ploughs ploughed ploughing pyjamas
aluminium sceptic sceptics sceptical scepticism aeroplane aeroplanes mum mums mummy storey storeys
whisky whiskies draught draughts draughty gaol gaols cosy cosier cosiest cosily doughnut doughnuts
yoghurt yoghurts tonne tonnes ageing judgement judgements acknowledgement acknowledgements enrol
enrols enrolled enrolling enrolment instalment instalments fulfil fulfils fulfilment skilful wilful
wilfully distil distils enthral enthralled enthralling appal appalled appalling artefact artefacts
axe axes moustache moustaches omelette omelettes pedlar practise practises practised practising
speciality specialities titbit titbits sulphur sulphuric sulphate sulphide phoney jewellery
jeweller jewellers dreamt learnt spelt spoilt burnt leant smelt favourite favourites maths
orientate orientated furore kilogramme gramme grammes carburettor marvellous marvellously woollen
counsellor counsellors chilli chillies liquorice mollusc molluscs fuelled fuelling dialled
dialling refuelled refuelling tranquilliser tranquillisers tranquillise tranquillised
apologise apologised apologises apologising recognise recognised recognises recognising
organisation organisations civilisation civilisations colourful colourfully colourless coloured
colouring colours honourable honourably favourable favourably behavioural labourer labourers
neighbourhood neighbourhoods neighbouring humoured harbouring flavoured flavouring savoury
paralyse paralysed paralysing analyse analysed analysing catalyse breathalyser hydrolyse
"""
_ISE = re.compile(r"^(.{3,})iz(e|es|ed|ing|er|ers|ation|ations|ational|able)$")
_YSE = re.compile(r"^(.{3,})yz(e|es|ed|ing|er|ers)$")
_DOUBLE_L = re.compile(r"^(.*[^aeiou][aeiou])l(ed|ing|er|ers|ist|ists)$")


def british_variants(known_words: Iterable[str]) -> set[str]:
    """British spellings to add: the explicit lists plus rule-made forms of
    every American word in `known_words` that has a regular counterpart."""
    out = set(_EXPLICIT.split())
    for stem in _OUR_STEMS:
        for suffix in _OUR_SUFFIXES:
            out.add(stem + suffix)
    for w in known_words:
        if m := _ISE.match(w):
            out.add(f"{m.group(1)}is{m.group(2)}")
        elif m := _YSE.match(w):
            out.add(f"{m.group(1)}ys{m.group(2)}")
        if m := _DOUBLE_L.match(w):
            out.add(f"{m.group(1)}ll{m.group(2)}")
    return out


# --------------------------------------------------------------------------- #
# The checker
# --------------------------------------------------------------------------- #
_engine = None
_engine_lock = threading.Lock()


def _load_engine():
    """pyspellchecker's English list plus the British variants, loaded once."""
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from spellchecker import SpellChecker

                sp = SpellChecker(language="en")
                sp.word_frequency.load_words(british_variants(sp.word_frequency.words()))
                _engine = sp
    return _engine


def available() -> bool:
    try:
        _load_engine()
        return True
    except Exception:
        return False


class Spellchecker:
    def __init__(self, ignore: Iterable[str] = ()) -> None:
        self._sp = _load_engine()
        self.ignore = {w.strip().lower() for w in ignore if w.strip()}

    def known(self, word: str) -> bool:
        w = word.lower()
        return w in self.ignore or w in self._sp

    def check(self, text: str) -> list[Suspect]:
        """Suspects in one line of text, with their offsets."""
        out: list[Suspect] = []
        for m in _HYPHEN_TOKEN.finditer(text):
            token, start = m.group(0), m.start()
            offset = 0
            for part in token.split("-"):
                if part:
                    out.extend(self._check_part(part, start + offset))
                offset += len(part) + 1
        return out

    def _check_part(self, part: str, start: int) -> list[Suspect]:
        word = part.replace("’", "'")
        if len(word) <= 1 or word[0].isdigit():  # a lone letter; a number, 1st, 1990s
            return []
        bare = word[:-2] if word.lower().endswith("'s") else word
        if not bare or bare.lower() in self.ignore:
            return []
        if any(ch.isdigit() for ch in bare):  # letters with a digit inside: me1ting, 0ur
            return [Suspect(part, start, start + len(part))]
        if bare.isupper() and len(bare) <= 5 and bare.lower() not in self._sp:
            return []  # an acronym, most likely
        if self.known(bare):
            return []
        return [Suspect(part, start, start + len(part))]

    def check_pages(
        self, pages: list[list[str]], name_pages: int = NAME_PAGES
    ) -> list[list[list[Suspect]]]:
        """Suspects for every line of every page, with the document-wide
        name rule: a capitalised unknown on `name_pages` or more pages is a
        name, not a suspect."""
        raw = [[self.check(line) for line in lines] for lines in pages]
        seen_on: dict[str, set[int]] = {}
        for pi, page in enumerate(raw):
            for line in page:
                for s in line:
                    if s.word[:1].isupper() and not s.word.isupper():
                        seen_on.setdefault(s.word.lower(), set()).add(pi)
        names = {w for w, on in seen_on.items() if len(on) >= name_pages}
        if not names:
            return raw
        return [[[s for s in line if s.word.lower() not in names] for line in page] for page in raw]

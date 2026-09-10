from usefultext.spellcheck import Spellchecker, Suspect, british_variants


def words(suspects):
    return [s.word for s in suspects]


def test_flags_misreads_and_names_but_not_english():
    sp = Spellchecker()
    line = "Two hundred sixty-cight penguins lived in the me1ting iceberg, said Kotter."
    got = sp.check(line)
    assert words(got) == ["cight", "me1ting", "Kotter"]
    cight = got[0]
    assert line[cight.start : cight.end] == "cight"  # offsets point into the line
    assert (
        sp.check("The penguins don't know; it's Fred's idea, NASA said.") == []
    )  # contractions, possessive, acronym
    assert sp.check("Chapter 3, page 10, the 1990s, 2nd edition") == []  # numbers never


def test_british_and_australian_spellings_are_known():
    sp = Spellchecker()
    text = (
        "The colour of the centre programme was grey; they organised, realised and analysed "
        "their favourite theatre catalogue, travelling with a licence to practise and "
        "neighbours in defence of the organisation's jewellery, mum."
    )
    assert sp.check(text) == []
    assert "colour" in british_variants([]) and "organise" in british_variants(["organize"])
    assert "travelled" in british_variants(["traveled"]) and "healled" not in british_variants(
        ["healed"]
    )


def test_ignore_list_and_offsets_with_apostrophes():
    sp = Spellchecker(ignore=["Kotter", " NoNo "])
    assert sp.check("Kotter and NoNo agreed; Rathgeber's plan") == [Suspect("Rathgeber's", 24, 35)]


def test_recurring_capitalised_words_are_names():
    sp = Spellchecker()
    pages = [
        ["Kotter looked at the iceberg.", "So did Rathgeber."],
        ["Kotter was worried.", "The cight penguins."],
        ["Kotter spoke to NoNo."],
    ]
    got = sp.check_pages(pages, name_pages=3)
    assert [[words(line) for line in page] for page in got] == [
        [[], ["Rathgeber"]],
        [[], ["cight"]],
        [["NoNo"]],
    ]
    # below the threshold everything stays a suspect
    assert words(sp.check_pages(pages[:2], name_pages=3)[0][0]) == ["Kotter"]

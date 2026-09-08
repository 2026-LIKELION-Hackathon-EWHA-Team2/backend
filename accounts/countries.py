import pycountry


COUNTRY_CHOICES = sorted(
    (country.alpha_2, country.name)
    for country in pycountry.countries
)

COUNTRY_ALIASES = {
    "일본": "JP",
    "日本": "JP",
    "대한민국": "KR",
    "한국": "KR",
    "SOUTH KOREA": "KR",
    "미국": "US",
    "USA": "US",
    "UNITED STATES": "US",
    "UNITED STATES OF AMERICA": "US",
    "중국": "CN",
    "CHINA": "CN",
}


def normalize_country(value):
    value = value.strip().upper()
    value = COUNTRY_ALIASES.get(value, value)

    country = (
        pycountry.countries.get(alpha_2=value)
        or pycountry.countries.get(alpha_3=value)
    )

    if country is None:
        try:
            country = pycountry.countries.lookup(value)
        except LookupError:
            raise ValueError(
                "유효한 국가명 또는 국가 코드를 입력해주세요."
            ) from None

    return country.alpha_2
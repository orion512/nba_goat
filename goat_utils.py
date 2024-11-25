"""
Utils module to scrape data for determinig the GOAT of the NBA
"""

import requests
from bs4 import BeautifulSoup


def parse_num_mvp(soup: BeautifulSoup, max_mvp: int) -> tuple[int, list[int]]:
    """
    Parses a BeautifulSoup element to find years where the player received an MVP award
    up to the given maximum MVP count (e.g., MVP-1, MVP-2, ..., MVP-{max_mvp}).
    
    Args:
        soup (BeautifulSoup): The parsed BeautifulSoup object containing the HTML.
        max_mvp (int): The maximum MVP count to filter awards (e.g., MVP-1, MVP-2).
        
    Returns:
        Tuple[int, List[int]]: A tuple containing the number of valid MVP awards found
                               and a list of the corresponding years.
    """
    rows = soup.select('#per_game_stats tr')
    years = []

    for row in rows:
        # Get the year from <th data-stat="year_id">
        year_th = row.select_one('th[data-stat="year_id"] a')
        year = year_th.text if year_th else None

        # Get the awards from <td data-stat="awards">
        awards_td = row.select_one('td[data-stat="awards"]')
        awards = awards_td.text if awards_td else None

        # Check if the award is an MVP with a number <= max_mvp
        
        
        if year and awards:
            mvp_awards = [award for award in awards.split(',') if 'MVP-' in award]
            
            if len(mvp_awards) > 1:
                raise Exception('More than 1 MVP in a year?')
            elif len(mvp_awards) == 0:
                continue
            else:
                mvp_award = mvp_awards[0]
                top_n = int(mvp_award.split('-')[1])
                if top_n <= max_mvp:
                    years.append(year)

    return len(years), years


def extract_team_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    """Extracts full team URLs from the soup."""
    rows = soup.select('#per_game_stats tr')
    team_urls = [
        row.select_one('td[data-stat="team_name_abbr"] a')['href']
        for row in rows
        if row.select_one('td[data-stat="team_name_abbr"] a')
    ]
    return [f"{base_url}{url}" for url in team_urls]


def get_top_regular_season_per_players(soup: BeautifulSoup, top_n: int = 5) -> list[tuple[str, float, str]]:
    """Retrieve top N players by PER in the regular season among the top 8 players by minutes played."""
    
    # Remove the comments from the HTML
    html_text = str(soup)
    cleaned_html_text = html_text.replace('<!--', '').replace('-->', '')
    cleaned_soup = BeautifulSoup(cleaned_html_text, 'html.parser')
    
    table = cleaned_soup.select_one('#advanced')
    if not table:
        return []  # Return an empty list if the table is not found

    players = []
    for row in table.select('tbody tr'):
        name_tag = row.select_one('td[data-stat="name_display"] a')
        minutes_tag = row.select_one('td[data-stat="mp"]')
        per_tag = row.select_one('td[data-stat="per"]')

        if per_tag.text.strip() == '':
            continue

        if name_tag and minutes_tag and per_tag:
            name = name_tag.text.strip()
            href = name_tag['href'] if 'href' in name_tag.attrs else None
            minutes = int(minutes_tag.text.strip())
            per = float(per_tag.text.strip())
            
            players.append((name, per, href, minutes))

    # Sort by minutes played and select the top 8 players
    top_minutes_players = sorted(players, key=lambda x: x[3], reverse=True)[:8]

    # From the top 8 by minutes, select the top N by PER
    return sorted(top_minutes_players, key=lambda x: x[1], reverse=True)[:top_n]


def get_top_playoff_per_players(soup: BeautifulSoup, top_n: int = 5) -> list[tuple[str, float, str]]:
    """Retrieve top N players by PER in playoffs among the top 8 players by minutes played."""
    
    # Remove the comments from the HTML
    html_text = str(soup)
    cleaned_html_text = html_text.replace('<!--', '').replace('-->', '')
    cleaned_soup = BeautifulSoup(cleaned_html_text, 'html.parser')
    
    table = cleaned_soup.select_one('#advanced_post')
    if not table:
        return []  # Return an empty list if the team didn't make the playoffs

    players = []
    for row in table.select('tbody tr'):
        name_tag = row.select_one('td[data-stat="name_display"] a')
        minutes_tag = row.select_one('td[data-stat="mp"]')
        per_tag = row.select_one('td[data-stat="per"]')

        if per_tag.text.strip() == '':
            continue

        if name_tag and minutes_tag and per_tag:
            name = name_tag.text.strip()
            href = name_tag['href'] if 'href' in name_tag.attrs else None
            minutes = int(minutes_tag.text.strip())
            per = float(per_tag.text.strip())
            
            players.append((name, per, href, minutes))

    # Sort by minutes played and select the top 8 players
    top_minutes_players = sorted(players, key=lambda x: x[3], reverse=True)[:5]

    # From the top 8 by minutes, select the top N by PER
    return sorted(top_minutes_players, key=lambda x: x[1], reverse=True)[:top_n]


def parse_team_playoff_result(soup: BeautifulSoup) -> str:
    """Parse how far the team made it in the playoffs."""
    meta_div = soup.select_one('#meta')
    if not meta_div:
        return "other"  # Default if meta section not found

    # Find the paragraph mentioning NBA Playoffs
    playoffs_paragraph = next(
        (p for p in meta_div.find_all('p') if "NBA" in p.text and "Playoffs" in p.text), None
    )
    if not playoffs_paragraph:
        return "other"  # Default if no playoffs paragraph is found

    # Check for specific playoff results (case insensitive, both conferences)
    text = playoffs_paragraph.text.lower()
    if "won nba finals" in text:
        return "champions"
    elif "won nba western conference finals" in text or "won nba eastern conference finals" in text:
        return "conference champions"
    elif "conference finals" in text:
        return "conference finals"
    else:
        return "other"  # For first-round exits or no playoffs


def rank_on_team(org_url_id: str, reg_season: list, playoffs: list, season_per_weight: float, playoff_per_weight: float, co_margin: float) -> str:
    """
    Decide the rank of the player on the team based on the PER
    of during the regular season and the playoffs.
    """
    combined = {}
    
    # Add season data
    for player, per, url, minutes in reg_season:
        combined[url] = {'name': player, 'season_per': per, 'playoff_per': 0, 'combined_per': per * season_per_weight}
    
    # Add playoff data and adjust combined PER
    for player, per, url, minutes in playoffs:
        if url in combined:
            combined[url]['playoff_per'] = per
            combined[url]['combined_per'] += per * playoff_per_weight
        else:
            combined[url] = {'name': player, 'season_per': 0, 'playoff_per': per, 'combined_per': per * playoff_per_weight}
    
    # Convert the dictionary back to a list
    result = [(data['name'], round(data['combined_per'], 2), url) for url, data in combined.items()]

    # Sort by combined PER in descending order
    sorted_players = sorted(result, key=lambda x: x[1], reverse=True)
    
    # Determine ranks
    ranks = []
    for i, (name, combined_per, url_id) in enumerate(sorted_players):
        if i == 0:  # First player
            ranks.append((name, combined_per, url_id, "1"))
        elif i == 1 and abs(combined_per - sorted_players[0][1]) <= co_margin:
            # Co-best rank
            ranks[0] = (*ranks[0][:3], "1/2")  # Adjust the first player to "1/2"
            ranks.append((name, combined_per, url_id, "1/2"))
        else:
            ranks.append((name, combined_per, url_id, str(i + 1)))

    player_rank = [tup[3] for tup in ranks if org_url_id == tup[2]]
    player_rank = player_rank[0] if player_rank else None

    return player_rank
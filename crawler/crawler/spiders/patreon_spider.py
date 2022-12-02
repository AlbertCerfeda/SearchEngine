import scrapy
from scrapy_playwright.page import PageMethod
import re
import artist_dict


class PatreonSpider(scrapy.Spider):
    name = 'patreon'
    stat_matcher = re.compile(r'^(\d+)')

    start_urls = [
        'https://www.patreon.com/search?q=art',
        'https://www.patreon.com/search?q=music',
        'https://www.patreon.com/search?q=photography',
        'https://www.patreon.com/search?q=writing',
        'https://www.patreon.com/search?q=game',
        'https://www.patreon.com/search?q=technology',
        'https://www.patreon.com/search?q=fitness',
        'https://www.patreon.com/search?q=cooking',
        'https://www.patreon.com/search?q=travel',
        'https://www.patreon.com/search?q=education',
        'https://www.patreon.com/search?q=health',
        'https://www.patreon.com/search?q=politic',
        'https://www.patreon.com/search?q=podcast',
        'https://www.patreon.com/search?q=stream',
        'https://www.patreon.com/search?q=video',
    ]


    custom_settings = {
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOAD_HANDLERS": {
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        "LOG_LEVEL": "INFO",
    }

    def start_requests(self):
        """Start the requests with playwright, so we can wait for the page to load."""
        for url in self.start_urls:
            yield scrapy.Request(url, meta={
                'playwright': True,
                'playwright_include_page': True,
                'playwright_page_methods': [
                    PageMethod('wait_for_selector', 'div[data-tag="campaign-result"]')
                ],
                'errback': self.errback,
            })

    async def parse(self, response):
        """Parse the search results page to get the artist's name, short description, image, etc."""
        page = response.meta['playwright_page']
        await page.close()

        print('\033[92m' + "Parsing: " + response.url + '\033[0m')

        # parse url to guess category
        tag = response.url.split('search?q=')[1]
        tag = tag.split('&')[0]
        tags = [tag]

        for artist in response.css('div[data-tag="campaign-result"]'):
            name = artist.css('span::text').get()
            url = artist.css('a::attr(href)').get()
            image = artist.css('div[data-tag="campaign-result-avatar"]::attr(src)').get()
            posts = artist.css('p.sc-jrQzAO.DzYUV::text').get()
            patrons = self.stat_matcher.search(artist.css('p[data-tag="campaign-result-patron-count"]::text').get(default=""))
            short_desc = artist.css('p.sc-jrQzAO.bsIqPC::text').get()


            # parse posts and patrons as int
            posts = int(self.stat_matcher.search(posts).group(1))
            if patrons:  # patrons number might be missing (private)
                patrons = int(patrons.group(1))

            # follow the artist's page to get the long description, pricing, etc.
            yield scrapy.Request(url, callback=self.parse_artist, meta={
                'name': name,
                'image': image,
                'posts': posts,
                'patrons': patrons,
                'short_desc': short_desc,
                'tags': tags,
            })

        # the next page is the first link after the current page
        next_page = response.css('div.sc-exfcb4-1.cAQEhl + a::attr(href)').get()

        if next_page is not None:
            yield scrapy.Request(next_page, meta={
                'playwright': True,
                'playwright_include_page': True,
                'playwright_page_methods': [
                    PageMethod('wait_for_selector', 'div[data-tag="campaign-result"]')
                ],
                'errback': self.errback,
            })

    def parse_artist(self, response):
        """Parse the artist's page to get the long description, pricing, etc."""
        print('\033[90m' + "\tParsing: " + response.url + '\033[0m')

        pricing = list(map(lambda tier:
                           artist_dict.make_price_tier(tier.css('div.sc-bkkeKt.cupyBO::text').get(),
                                                       tier.css('h3[data-tag="tier-title"]::text').get(),
                                                       ' '.join(tier.css('.sc-1rlfkev-0.MtGiR *::text').getall()))
                           , response.css('div[data-tag="reward-tier-card"]')))
        long_desc = response.css('div[data-tag="summary-container"] *::text').getall()
        long_desc = ' '.join(long_desc)



        scraped = artist_dict.make(
            self.name,
            response.url,
            response.meta['name'],
            response.meta['image'],
            response.meta['short_desc'],
            long_desc,
            response.meta['posts'],
            response.meta['patrons'],
            pricing,
            response.meta['tags'],
            response.css('div[data-tag="campaign-social-links"] a[role="button"]::attr("href")').getall(),
            ""#response.css('div[data-tag="cover-photo-container"]')
        )

        # print(scraped)
        yield scraped;

    async def errback(self, failure):
        page = failure.request.meta["playwright_page"]
        await page.close()

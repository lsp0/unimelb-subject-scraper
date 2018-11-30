import scrapy	

def parse_element(element):
	""" Function can return None, be careful!"""
	# traverse list (if element is one)
	ul = element.xpath(".//li")
	if len(ul) != 0:
		return {"type" : "list", "val" : ul.css("::text").extract()}
	# treat as just text	
	string = element.xpath("string(.)").extract_first().strip()
	# TODO: possibly check if it is a "\n" and turn it into a 'None' ?
	if string == "None" or string == "Nil" or string == "":
		return None
	if string == "\n  ":
		print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
		return None
	return {"type" : "text", "val" : string}

def parse_element_with_subject_table(element):
	# traverse table (if element is one)
	table = element.xpath(".//tr")
	if len(table) != 0:
		current = {"type" : "subj", "val" : []}
		for row in table[1:]:
			# take only the subject code
			current["val"].append(row.css("td::text").extract_first())
		return current
	return parse_element(element)

class SubjectsSpider(scrapy.Spider):
	name = 'subjects'
	#start_urls = ['https://handbook.unimelb.edu.au/search?query=&year=2018&types%5B%5D=subject&level_type%5B%5D=undergraduate&study_periods%5B%5D=semester_1&study_periods%5B%5D=semester_2&study_periods%5B%5D=summer_term&study_periods%5B%5D=winter_term&study_periods%5B%5D=year_long&area_of_study=all&faculty=all&department=all']
	#start_urls = ['https://handbook.unimelb.edu.au/subjects/undergraduate']
	#start_urls = ['https://handbook.unimelb.edu.au/breadth-search?course=B-SCI']
	start_urls = ['https://handbook.unimelb.edu.au/subjects/']
	parse_count = 0
	parsed_count = 0
	total_count = 0
	
	def parse_date_info(self, response):
		data = response.meta['data']

		yield data

	def parse_assessment(self, response):
		data = response.meta['data']
		assessment = {}
		table = response.css(".assessment-table tr")
		assessment["assessments"] = []
		if len(table) != 0:
			for row in table[1:]:
				current = {}
				a = row.css("td")[0].css("li::text").extract()
				current["name"] = a[0].strip()
				current["info"] = a[1:]
				a = row.css("td::text").extract()
				current["timing"] = a[0]
				current["weight"] = a[1]
		description_body = response.css(".assessment-description > *")
		if len(description_body) != 0:
			description = []
			for element in description_body[1:]:
				string = parse_element(element)
				if string is not None:
					description.append(string)
			assessment["description"] = description
		data["assessment"] = assessment
		
		self.parsed_count += 1
		print("[{:4d}/{:4d}/{:4d}] (-) Parsed  ({:4d}) {}  {}".format(self.parsed_count, self.parse_count, self.total_count, data['no'], data['code'], data['name']))

		yield data

	def parse_requirements(self, response):
		data = response.meta['data']
		requirements = {}
		# handle prerequisites
		prereq_body = response.css("#prerequisites > *")[1:]
		prereq = []
		for element in prereq_body:
			parsed = parse_element_with_subject_table(element)
			if parsed is not None:
				prereq.append(parsed)
		requirements['Prerequisites'] = prereq
		# handle corequisites, non-allowed subjects, recommended background knowledge
		# Take each element of the body, except the title and 'core participation req.' stuff
		body = response.css('div.course__body > *')[2:-4]
		# Include recommended background knowledge - not every page has it.
		requirements['Recommended background knowledge'] = []
		section_name = ""
		for element in body:
			extracted = element.extract()
			if extracted[:3] == "<h3":
				section_name = element.css("::text").extract_first()
				requirements[section_name] = []
				continue
			parsed = parse_element_with_subject_table(element)
			if parsed is not None:
				requirements[section_name].append(parsed)
		data["requirements"] = requirements
		yield scrapy.Request(
			response.urljoin(data["url"] + '/assessment'),
			callback=self.parse_assessment,
			meta={'data': data}
		)
		
	def parse_subject(self, response):
		data = response.meta['data']
		data['weight'] = response.css('p.header--course-and-subject__details span ::text').extract()[1].split("Points: ")[1]
		# Parse infobox
		for line in response.css('div.course__overview-box tr'):
			field = line.css('th ::text').extract_first()
			value = line.css('td').xpath("string(.)").extract_first()
			if field == 'Availability':
				data[field] = [label.css("::text").extract_first() for label in line.xpath('.//td/div')]
			# don't parse these
			elif field == 'Fees' or field == "Year of offer" or field == "Subject code":
				pass
			else:
				data[field] = value
		# Parse overview paragraphs
		data['overview'] = response.css(".course__overview-wrapper > p").xpath("string(.)").extract()
		data['learning-outcomes'] = response.css("#learning-outcomes .ticked-list li ::text").extract()
		data['skills'] = response.css("#generic-skills .ticked-list li ::text").extract()
		# Get 'last updated' from page
		data['updated'] = response.css(".last-updated ::text").extract_first()[14:]
		yield scrapy.Request(
			response.urljoin(data["url"] + '/eligibility-and-requirements'),
			callback=self.parse_requirements,
			meta={'data': data}
		)
	# parses results page, list of subjects
	def parse(self, response):
		# follow links to subject pages
		for result in response.css('li.search-results__accordion-item'):
			self.total_count += 1
			# skip if subject is not offered.
			offered = result.css('span.search-results__accordion-detail ::text').extract()[1]
			if ("Not offered in" in offered):
				continue
			self.parse_count += 1
			data = {}
			data['no_total'] = self.total_count
			data['no'] = self.parse_count
			data['name'] = result.css('a.search-results__accordion-title ::text').extract_first()
			data['code'] = result.css('span.search-results__accordion-code ::text').extract_first()
			data['url'] = result.css('a.search-results__accordion-title ::attr(href)').extract_first()
			print("[{:4d}/{:4d}/{:4d}] (+) Parsing ({:4d}) {}  {}".format(self.parsed_count, self.parse_count, self.total_count, data['no'], data['code'], data['name']))

			yield scrapy.Request(
					response.urljoin(data['url']),
					callback=self.parse_subject,
					meta={'data': data}
				)

		# follow pagination links to next list of subjects
		next_page = response.css('span.next a ::attr(href)').extract_first()
		if next_page is not None:
			print("Page exhausted. Navigate to", next_page)
			yield response.follow(next_page, self.parse)
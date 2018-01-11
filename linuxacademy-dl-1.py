from selenium import webdriver
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
import pandas as pd
import requests
import wget
import re
import csv
from bs4 import BeautifulSoup
import os, os.path
import logging
import time
import sys
### GLOBAL VARIABLES
COURSE_PATH = '../inputs/input.csv'

username = 'PUT YOUR LA USERNAME'
password = 'PUT YOUR PWD'
delay = 60
path_to_chromedriver = "PATH TO chromedriver.exe"
logging.basicConfig(filename='../logs/py-download-videos-%s.log'%time.time(),level=logging.INFO)
logging.basicConfig(filename='../logs/download-videos-debug-%s.log'%time.time(),level=logging.DEBUG)


#This performs login
def login():
	global username
	global password
	
	try:
		myElem = WebDriverWait(browser, delay).until(EC.presence_of_element_located((By.NAME, 'username')))
		logging.info("LOGIN: Course page  ready")
		print("LOGIN: Course page  ready")
	except TimeoutException:
		logging.info("LOGIN: Course page timeout")
		print("LOGIN: Course page timeout")

	browser.find_element_by_name('username').send_keys(username)
	browser.find_element_by_name('password').send_keys(password)
	browser.find_element_by_class_name('auth0-lock-submit').click()
	logging.info("LOGIN: Login button clicked")
	print("LOGIN: Login button clicked")

#This creates a html file containing the syllabus source
def save_course_syllabus(coursename, browser):
	try:
		myElem = WebDriverWait(browser, delay).until(EC.presence_of_element_located((By.CLASS_NAME, 'syllabus-item')))
		logging.info("%s syllabus OK" %coursename)
		print("%s syllabus OK" %coursename)
		time.sleep(2)
		
		with open('../middles/%s/%s_syllabus.html'%(coursename,coursename),'w',encoding='utf-8') as output:
			output.write(browser.page_source)
	except TimeoutException:
		logging.info("%s syllabus timeout"%coursename)
		print("%s syllabus timeout"%coursename)
		return False
	return True

	
#This generates a table which contains "lecturename, lectureurl".
def get_lecture_urls(coursename):
	with open('../middles/%s/%s_syllabus.html'%(coursename,coursename),'rb') as inputf:
		soup = BeautifulSoup(inputf,'html.parser')

	list_div1 = soup.find_all('div', 'col-xs-9 col-sm-10')
	list_div2 = soup.find_all('div', 'col-xs-3 col-sm-2')

	cols = ['lecturename','lecturehef','time']
	df = pd.DataFrame(columns = cols)
	if len(list_div1)==len(list_div2):
		cnt = 1
		for div1, div2 in zip(list_div1, list_div2):
			a = div1.find('a')
			p = div2.find('p')
			
			atext = str(a.text).strip()
			ahref = str(a['href']).strip()
			ptext = str(p.text).strip()
			atext = re.sub(r'([^\s\w]|_)+', '', atext)
			atext = str(cnt)+'-'+atext
			
			df_tmp = pd.DataFrame([[atext, ahref, ptext]], columns=cols)
			df = df.append(df_tmp)
			cnt +=1
		df = df[df['time'].str.contains(":")]
		df.to_csv('../middles/%s/%s-lecture-urls.csv'%(coursename,coursename),sep=',',index=False)
	return df

def get_segment_url(coursename, df_lectureurls):
	global delay
	
	with open('../middles/%s/%s-segment-urls.csv'%(coursename,coursename),'w', newline='') as f:
		writer = csv.writer(f)
		writer.writerow(['lecturename', 'segment_url','chunk_url'])
	for index, row in df_lectureurls.iterrows():
		lecturename = row['lecturename']
		lecturehef = row['lecturehef']
		try:
			myElem = WebDriverWait(browser, delay).until(EC.presence_of_element_located((By.CLASS_NAME, 'syllabus-item')))
			logging.info("%s Syllabus is ready!" %coursename)
			print("%s Syllabus is ready!" %coursename)
		except TimeoutException:
			logging.debug("%s Syllabus timeout!" %coursename)
			print("%s Syllabus timeout!" %coursename)
		time.sleep(5)
		elem = browser.find_element_by_xpath('//a[@href="'+lecturehef+'"]');
		elem.click()
		time.sleep(5)
		
		segment_url = []
		chunk_url =[]
		tries = 0
		while (len(segment_url) < 1 or len(chunk_url) <1) and tries <3:
			time.sleep(3)
			reqs = browser.execute_script("""return performance.getEntries().filter(e => e.entryType==='resource').map(e=> (e.name));""")
			segment_url = [s for s in reqs if "_0.ts?" in s]
			chunk_url = [s for s in reqs if "chunklist_b" in s]
			tries +=1
		
		if len(segment_url) > 0 and len(chunk_url) > 0:
			logging.info("%s > %s > %s" %(coursename, lecturename, segment_url[0]))
			print("%s > %s > %s" %(coursename, lecturename, segment_url[0]))
			with open('../middles/%s/%s-segment-urls.csv'%(coursename,coursename),'a', newline='') as f:
				writer = csv.writer(f)
				writer.writerow([lecturename, segment_url[0], chunk_url[0]])
		else:
			logging.debug("%s %s segment url =0" %(coursename, lecturename))
			print("%s %s segment url =0" %(coursename, lecturename))
		browser.execute_script("window.history.go(-1)")
	
	df_segment_urls = pd.read_csv('../middles/%s/%s-segment-urls.csv'%(coursename,coursename), sep=',')
	return df_segment_urls
	
# This will return the number of chunks of a lecture

def get_chunk_number(chunk_url):
	with open(chunk_url,'r') as chunklist:
		s = chunklist.read()
	s = re.sub(r'[\n\r]+', '', s)
	match = re.search(r".*\_(.*)\.ts", s)
	print("Chunk number: %s" %match.group(1))
	logging.info("Chunk number: %s" %match.group(1))
	return int(match.group(1))
		
		
#This downloads segments of a lecture and concatenates the segments.
def download_lecture(coursename, df_segment_urls):
	OUTPUTDIR = '../downloads/'+coursename+'/'
	if not os.path.exists(OUTPUTDIR):
		os.makedirs(OUTPUTDIR)
	
	for index, row in df_segment_urls.iterrows():
		
		try_download = 0
		try_chunk =0
		lecturename = row['lecturename']
		lectureurl = row['segment_url']
		lectureurl = re.split(r'\_0.ts+',lectureurl)
		lectureurl_prefix = lectureurl[0]
		lectureurl_suffix = lectureurl[1]
		lecturepath = OUTPUTDIR+lecturename+'/'
		chunk_number = 1 #If chunklist is not read, it will download only 1 segment.
		logging.info('Download: %s %s' %(lecturename, lectureurl))
		print('Download: %s %s' %(lecturename, lectureurl))
		
		# Get chunk list to determine total number of segments
		while try_chunk < 3:
			try:
				r = requests.get(row['chunk_url'], timeout=2)
				chunkpath = '../middles/'+coursename+'/'+'chunklist_'+lecturename
				if r.status_code==200:
					wget.download(row['chunk_url'],chunkpath)
					break
				else:
					try_chunk +=1
			except:
				logging.debug('chunklist download failed: %s %s %s'%(coursename,lecturename,index))
				try_chunk +=1
		
					
		# Download segments		
		
		if not os.path.exists(lecturepath):
			os.makedirs(lecturepath)
		
		chunk_number = get_chunk_number(chunkpath)+1
		for cnt in range(0, chunk_number):
			while try_download < 3:
				try:
					lecture_elem = lectureurl_prefix +'_'+ str(cnt) + '.ts' + lectureurl_suffix
					print(lecture_elem)
					r = requests.get(lecture_elem, timeout=2)
					if r.status_code ==200:
						wget.download(lecture_elem, lecturepath+lecturename+'_'+str(cnt)+'.ts')
						break
					else:
						try_download +=1
				except:
					time.sleep(2)
					logging.debug('Slept 2secs, chunklist download failed: %s %s chunk: %s'%(coursename,lecturename,str(cnt)))
					try_download +=1
			
			
		# Merge segment files
		with open(OUTPUTDIR+lecturename+'.ts', "wb") as outputf:
			for i in range(0,chunk_number):
				input = lecturepath+lecturename+'_'+str(i)+'.ts'
				try:
					with open(input, "rb") as inputf:
						outputf.write(inputf.read())
				except:
					logging.info('BUG: %s not created' %lecturename)

if __name__ == "__main__":
	
	sys_option = sys.argv[1]
	# option: 1- Default, run entire script; 2- read directly from lecture urls; 3- read directly from segment urls. 
	
	if sys_option == '1':
		print('option == 1')
		df_courses = pd.read_csv(COURSE_PATH,sep=',')
		for index, row in df_courses.iterrows():
			browser = webdriver.Chrome(executable_path = path_to_chromedriver)
			coursename = row['coursename']
			courseurl = row['courseurl']
			logging.info("Course name: %s"%coursename)
			logging.info("Course url: %s"%courseurl)
			print("Course name: %s"%coursename)
			print("Course url: %s"%courseurl)
			if not os.path.exists('../downloads/'+coursename):
				os.makedirs('../downloads/'+coursename)
			if not os.path.exists('../middles/'+coursename):
				os.makedirs('../middles/'+coursename)
			
			browser.get(courseurl)
			login()
			
			if save_course_syllabus(coursename, browser):
				df_lectureurls = get_lecture_urls(coursename)
				df_segment_urls = get_segment_url(coursename, df_lectureurls)
				browser.close()
				download_lecture(coursename, df_segment_urls)
			
	elif sys_option == '2':
		print('option == 2')
		sys_coursename = sys.argv[2]
		sys_courseurl = sys.argv[3]
		print(sys_coursename)
		print(sys_courseurl)
		browser = webdriver.Chrome(executable_path = path_to_chromedriver)
		browser.get(sys_courseurl)
		login()
		if os.path.exists('../middles/%s/%s-lecture-urls.csv'%(sys_coursename,sys_coursename)):
			df_lectureurls = pd.read_csv('../middles/%s/%s-lecture-urls.csv'%(sys_coursename,sys_coursename),sep=',')
			df_lectureurls = df_lectureurls[df_lectureurls['time'].str.contains(":")]
			df_segment_urls = get_segment_url(sys_coursename, df_lectureurls)
			browser.close()
			download_lecture(sys_coursename, df_segment_urls)
	
	elif sys_option == '3':
		print('option == 3')
		sys_coursename = sys.argv[2]
		sys_courseurl = sys.argv[3]
		print(sys_coursename)
		print(sys_courseurl)
		if os.path.exists('../middles/%s/%s-segment-urls.csv'%(sys_coursename,sys_coursename)):
			df_segment_urls = pd.read_csv('../middles/%s/%s-segment-urls.csv'%(sys_coursename,sys_coursename), sep=',')
			download_lecture(sys_coursename, df_segment_urls)
			
		
		
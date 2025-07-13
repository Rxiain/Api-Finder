"""
@date: 2025
@version: 0.3.1
@description: 用于扫描API端点
"""

import random
import requests
from urllib.parse import urlparse
from bs4 import BeautifulSoup
import argparse
import time
import sys
import json
import os
from datetime import datetime
from urllib3.exceptions import InsecureRequestWarning
import urllib3
from .ua_manager import UaManager
from .utils import URLProcessor, URLExtractor, UpdateManager
from .i18n import i18n
from .output_manager import OutputManager, FileOutputManager
import threading
import pyfiglet
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.align import Align
from rich.live import Live
from rich.status import Status
from rich.json import JSON
from rich.traceback import install
from rich.columns import Columns
from rich.rule import Rule

# 禁用SSL警告
urllib3.disable_warnings(InsecureRequestWarning)

# 安装Rich的异常处理
install()

parser = argparse.ArgumentParser(description="Api-Finder v0.3")
parser.add_argument("-u", "--url", help=i18n.get('arg_url_help'), required=True)
parser.add_argument("-c", "--cookie", help=i18n.get('arg_cookie_help'))
parser.add_argument("-p", "--proxy", help=i18n.get('arg_proxy_help'))
parser.add_argument("-s", "--silent", action="store_true", help=i18n.get('arg_silent_help'))
parser.add_argument("-o", "--output", help=i18n.get('arg_output_help'))
parser.add_argument("-t", "--timeout", type=int, default=10, help=i18n.get('arg_timeout_help'))
parser.add_argument("-d", "--delay", type=float, default=0.5, help=i18n.get('arg_delay_help'))
parser.add_argument("-v", "--verbose", action="store_true", help=i18n.get('arg_verbose_help'))
parser.add_argument("-r", "--random", action="store_true", help=i18n.get('arg_random_help'))
parser.add_argument("-a", "--app", help=i18n.get('arg_app_help'), default='common')
parser.add_argument("-U", "--update", action="store_true", help=i18n.get('arg_update_help'))
arg = parser.parse_args()

# 初始化Rich Console (Initialize Rich Console)
console = Console()

# 初始化UA管理器 (Initialize UA Manager)
Uam = UaManager(arg.app, arg.random)

# 使用Rich重构的Logo显示
def show_logo():
	"""使用Rich和pyfiglet显示精美logo"""
	try:
		# 生成ASCII art
		logo_text = pyfiglet.figlet_format("Api-Finder", font="slant")
		
		# 创建带颜色的logo文本
		logo = Text(logo_text, style="cyan bold")
		
		# 创建项目信息文本
		info_text = Text()
		info_text.append("API Endpoint Scanner v0.5", style="green bold")
		info_text.append("     Github: github.com/jujubooom/Api-Finder\n", style="blue")
		info_text.append("Developed by jujubooom,bx,orxiain", style="green bold")
		
		# 创建面板
		logo_panel = Panel(
			Align.center(logo),
			title="[yellow bold]🚀 API-Finder 🚀[/yellow bold]",
			border_style="cyan",
			padding=(1, 2)
		)
		
		info_panel = Panel(
			Align.center(info_text),
			border_style="green",
			padding=(0, 2)
		)
		
		# 显示logo和信息
		console.print(logo_panel)
		console.print(info_panel)
		console.print(Rule(style="dim"))
		
	except Exception as e:
		# 急救措施 - 使用简单的Rich显示
		console.print(Panel(
			"[cyan bold]Api-Finder v0.3[/cyan bold]\n"
			"[blue]Github: github.com/jujubooom/Api-Finder[/blue]",
			title="🚀 API-Finder 🚀",
			border_style="cyan"
		))



# 初始化输出管理器 (Initialize output manager)
output = OutputManager(arg.silent, arg.verbose, arg.output)
file_output = FileOutputManager(output)
proxies_global = None

def do_proxys():
	global proxies_global
	
	if proxies_global is not None:
		return proxies_global
	
	if arg.proxy == "0":
		# 自动获取代理列表 (Auto fetch proxy list)
		header = {"User-Agent": Uam.getUa()}
		proxy_response = requests.get("https://proxy.scdn.io/api/get_proxy.php?protocol=socks5&count=5", headers=header).text
		proxy_data = json.loads(proxy_response)
		if proxy_data.get("code") == 200 and "data" in proxy_data and "proxies" in proxy_data["data"]:
			proxies_global = proxy_data["data"]["proxies"]
		else:
			output.print_error(i18n.get('proxy_fetch_failed'))
			proxies_global = []

	elif arg.proxy:
		# 判断代理类型是否为socks5
		if arg.proxy.startswith('socks5://'):
			proxies_global = {
				"http": arg.proxy,
				"https": arg.proxy
			}
		# 普通http/https代理
		else:
			proxies_global = {
				"http": arg.proxy if arg.proxy.startswith('http') else f'http://{arg.proxy}',
				"https": arg.proxy if arg.proxy.startswith('http') else f'http://{arg.proxy}'
			}
	
	return proxies_global

# 创建线程安全的结果存储结构 (Create thread-safe result storage structure)
class ResultStore:
	def __init__(self):
		self.results = {"GET": {}, "POST": {}}
		self.lock = threading.Lock()

	def update(self, method, success, response_text, error=None):
		with self.lock:
			self.results[method] = {
				"success": success,
				"response": response_text,
				"error": error
			}


# 请求执行函数 (Request execution function)
def make_request(method, url, cookies, timeout, store):
	# 请求前的配置 (Request configuration)
	proxies = do_proxys()
	if proxies and isinstance(proxies, list):
		proxies = {
			"socks5": proxies[random.randint(0,len(proxies)-1)],
		}
	
	# 更完整的请求头
	header = {
		"User-Agent": Uam.getUa(),
		"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
		"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
		"Accept-Encoding": "gzip, deflate, br",
		"Connection": "keep-alive",
		"Upgrade-Insecure-Requests": "1",
		"Cache-Control": "max-age=0"
	}
	
	# 设置重试次数
	max_retries = 2
	retry_delay = 0.5
	
	for attempt in range(max_retries):
		try:
			# 配置session以处理SSL和连接问题
			session = requests.Session()
			session.verify = False  # 禁用SSL验证
			
			# 设置适配器以处理重试
			adapter = requests.adapters.HTTPAdapter(max_retries=1)
			session.mount('http://', adapter)
			session.mount('https://', adapter)
			
			# 添加代理支持
			if proxies:
				session.proxies.update(proxies)
			
			# 发送请求
			if method == "GET":
				res = session.get(
					url, 
					headers=header, 
					cookies=cookies, 
					timeout=(5, timeout),  # 连接超时5秒，读取超时使用参数
					allow_redirects=True
				)
			else:  # POST
				res = session.post(
					url, 
					headers=header, 
					cookies=cookies, 
					timeout=(5, timeout),  # 连接超时5秒，读取超时使用参数
					allow_redirects=True
				)

			res.raise_for_status()
			response_text = res.text.replace(" ", "").replace("\n", "")
			store.update(method, True, response_text)
			return
			
		except requests.exceptions.SSLError as e:
			if attempt < max_retries - 1:
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				store.update(method, False, None, f"SSL error: {str(e)}")
				return
				
		except requests.exceptions.ConnectionError as e:
			if attempt < max_retries - 1:
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				store.update(method, False, None, f"Connection error: {str(e)}")
				return
				
		except requests.exceptions.Timeout as e:
			if attempt < max_retries - 1:
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				store.update(method, False, None, f"Timeout: {str(e)}")
				return
				
		except requests.exceptions.RequestException as e:
			if attempt < max_retries - 1:
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				store.update(method, False, None, f"Request error: {str(e)}")
				return
				
		except Exception as e:
			if attempt < max_retries - 1:
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				store.update(method, False, None, f"Unexpected error: {str(e)}")
				return


def do_request(url):
	result_store = ResultStore()

	# 创建并启动线程
	get_thread = threading.Thread(
		target=make_request,
		args=("GET", url, {"Cookie": arg.cookie}, arg.timeout, result_store)
	)

	post_thread = threading.Thread(
		target=make_request,
		args=("POST", url, {"Cookie": arg.cookie}, arg.timeout, result_store)
	)

	# 启动线程
	get_thread.start()
	post_thread.start()

	# 等待两个线程完成
	get_thread.join()
	post_thread.join()
	
	response_text_to_return = None

	# 统一输出结果 (Unified output results)
	for method in ["GET", "POST"]:
		result = result_store.results[method]
		if result["success"]:
			response_text = result['response']
			
			if method == "GET":
				response_text_to_return = response_text
				# 尝试解析和打印标题
				try:
					if response_text and '<html' in response_text.lower():
						soup = BeautifulSoup(response_text, 'html.parser')
						if soup.title and soup.title.string:
							title = soup.title.string.strip().replace('\\n', '').replace('\\r', '')
							if title:
								output.print_title(url, title)
				except Exception as e:
					output.print_verbose(f"Could not parse title from {url}: {e}")

			if method == "GET" and output.silent_mode:
				output.console.print(url, highlight=False)
			elif not output.silent_mode:
				output.print_success(f"{method} request successful for {url}")
				if output.verbose_mode:
					res_len = len(response_text)
					output.print_verbose(f"📏 Response length: {res_len} characters")
					output.print_verbose(f"👀 Response preview: {response_text[:200]}...")

			output.stats["successful_requests"] += 1
		else:
			output.print_error(f"{method} request failed for {url}: {result['error']}")
			output.stats["failed_requests"] += 1
	
	# 请求间隔
	time.sleep(arg.delay)
	return response_text_to_return


# 获取HTML内容 (Extract HTML content)
def Extract_html(URL):
	"""
	URL: 目标URL (Target URL)
	header: 请求头 (Request headers)
	raw: 请求返回的内容 (Raw response content)
	content: 解析后的HTML内容 (Parsed HTML content)
	return: 返回HTML内容 (Return HTML content)
	"""
	# 更完整的请求头
	header = {
		"User-Agent": Uam.getUa(),
		"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
		"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
		"Accept-Encoding": "gzip, deflate, br",
		"Connection": "keep-alive",
		"Upgrade-Insecure-Requests": "1",
		"Sec-Fetch-Dest": "document",
		"Sec-Fetch-Mode": "navigate",
		"Sec-Fetch-Site": "none",
		"Cache-Control": "max-age=0"
	}
	
	# 设置重试次数
	max_retries = 3
	retry_delay = 1
	
	for attempt in range(max_retries):
		try:
			# 配置session以处理SSL和连接问题
			session = requests.Session()
			session.verify = False  # 禁用SSL验证
			
			# 设置适配器以处理重试
			adapter = requests.adapters.HTTPAdapter(max_retries=2)
			session.mount('http://', adapter)
			session.mount('https://', adapter)
			
			# 添加代理支持
			proxies = do_proxys()
			if proxies and isinstance(proxies, dict):
				session.proxies.update(proxies)
			
			# 发送请求
			raw = session.get(
				URL, 
				headers=header, 
				timeout=(10, 30),  # 连接超时10秒，读取超时30秒
				cookies=arg.cookie if arg.cookie else None,
				allow_redirects=True,
				stream=False
			)
			
			raw.raise_for_status()
			
			# 这里做了三个尝试，如果都失败，则返回None
			try:
				content = raw.content.decode("utf-8", "ignore")
			except UnicodeDecodeError:
				try:
					content = raw.content.decode("gbk", "ignore")
				except UnicodeDecodeError:
					content = raw.content.decode("latin-1", "ignore")
			
			output.print_verbose(f"✅ Successfully retrieved HTML content: {URL}")
			return content
			
		except requests.exceptions.SSLError as e:
			if attempt < max_retries - 1:
				output.print_verbose(f"🔄 SSL error on attempt {attempt + 1}, retrying: {URL}")
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				output.print_error(f"SSL error after {max_retries} attempts {URL}: {str(e)}")
				return None
				
		except requests.exceptions.ConnectionError as e:
			if attempt < max_retries - 1:
				output.print_verbose(f"🔄 Connection error on attempt {attempt + 1}, retrying: {URL}")
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				output.print_error(f"Connection error after {max_retries} attempts {URL}: {str(e)}")
				return None
				
		except requests.exceptions.Timeout as e:
			if attempt < max_retries - 1:
				output.print_verbose(f"🔄 Timeout on attempt {attempt + 1}, retrying: {URL}")
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				output.print_error(f"Timeout after {max_retries} attempts {URL}: {str(e)}")
				return None
				
		except requests.exceptions.RequestException as e:
			if attempt < max_retries - 1:
				output.print_verbose(f"🔄 Request error on attempt {attempt + 1}, retrying: {URL}")
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				output.print_error(f"Request failed after {max_retries} attempts {URL}: {str(e)}")
				return None
				
		except Exception as e:
			if attempt < max_retries - 1:
				output.print_verbose(f"🔄 Unexpected error on attempt {attempt + 1}, retrying: {URL}")
				time.sleep(retry_delay)
				retry_delay *= 2
				continue
			else:
				output.print_error(f"Unexpected error after {max_retries} attempts {URL}: {str(e)}")
				return None
	
	return None


def find_by_url(url):
	try:
		output.print_info(f"🎯 [bold blue]Starting scan target:[/bold blue] [green]{url}[/green]")
	except:
		output.print_info("❌ Please specify a valid URL, e.g.: https://www.baidu.com")
		return None
	
	# 使用状态显示
	if not output.silent_mode:
		with Status("[bold green]🔍 Fetching target page...", console=output.console):
			html_raw = Extract_html(url)
	else:
		html_raw = Extract_html(url)
	
	if html_raw == None: 
		output.print_error(f"Cannot access {url}")
		return None
	
	output.print_verbose("🔍 Starting to parse HTML content...")
	html = BeautifulSoup(html_raw, "html.parser")
	html_scripts = html.findAll("script")
	output.print_verbose(f"📄 Found {len(html_scripts)} script tags")
	
	script_array = {}
	script_temp = ""
	
	# 创建进度条来显示脚本处理进度
	progress = output.create_progress()
	if progress:
		with progress:
			script_task = progress.add_task("[cyan]📄 Processing scripts...", total=len(html_scripts))
			
			for html_script in html_scripts:
				script_src = html_script.get("src")
				if script_src == None:
					script_temp += html_script.get_text() + "\n"
				else:
					purl = URLProcessor.process_url(url, script_src)
					progress.update(script_task, description=f"[cyan]📄 Fetching: {purl.split('/')[-1]}")
					script_content = Extract_html(purl)
					if script_content:
						script_array[purl] = script_content
					else:
						output.print_warning(f"Cannot get external script: {purl}")
				
				progress.advance(script_task)
	else:
		# 静默模式或无进度条时的处理
		for html_script in html_scripts:
			script_src = html_script.get("src")
			if script_src == None:
				script_temp += html_script.get_text() + "\n"
			else:
				purl = URLProcessor.process_url(url, script_src)
				script_content = Extract_html(purl)
				if script_content:
					script_array[purl] = script_content
				else:
					output.print_warning(f"Cannot get external script: {purl}")
	
	script_array[url] = script_temp
	
	# 分析脚本以提取URL
	allurls = {}
	total_scripts = len(script_array)
	
	if not output.silent_mode:
		output.print_info(f"🔎 [bold yellow]Analyzing {total_scripts} scripts for API endpoints...[/bold yellow]")
	
	progress = output.create_progress()
	if progress:
		with progress:
			analyze_task = progress.add_task("[green]🔍 Analyzing scripts...", total=total_scripts)
			
			for script in script_array:
				script_name = script.split('/')[-1] if '/' in script else script
				progress.update(analyze_task, description=f"[green]🔍 Analyzing: {script_name}")
				
				output.print_verbose(f"🔎 Analyzing script: {script}")
				temp_urls = URLExtractor.extract_urls(script_array[script])
				
				if len(temp_urls) == 0: 
					output.print_verbose("🔍 No URLs found")
				else:
					output.print_verbose(f"✅ Found {len(temp_urls)} URLs")
					allurls[script] = temp_urls
				
				progress.advance(analyze_task)
	else:
		# 静默模式处理
		for script in script_array:
			output.print_verbose(f"🔎 Analyzing script: {script}")
			temp_urls = URLExtractor.extract_urls(script_array[script])
			if len(temp_urls) == 0: 
				output.print_verbose("🔍 No URLs found")
			else:
				output.print_verbose(f"✅ Found {len(temp_urls)} URLs")
				allurls[script] = temp_urls
	
	# 处理发现的URL
	total_urls = sum(len(urls) for urls in allurls.values())
	if total_urls > 0:
		output.print_info(f"🎯 [bold green]Found {total_urls} potential API endpoints. Testing them...[/bold green]")
		
		progress = output.create_progress()
		if progress:
			with progress:
				test_task = progress.add_task("[blue]🌐 Testing endpoints...", total=total_urls)
				
				for i in allurls:
					for j in allurls[i]:
						# 显示当前正在测试的URL
						url_display = j[:50] + "..." if len(j) > 50 else j
						progress.update(test_task, description=f"[blue]🌐 Testing: {url_display}")
						
						output.print_url(j, i)
						temp1 = urlparse(j)
						temp2 = urlparse(url)
						
						if temp1.netloc != urlparse("1").netloc:
							do_request(j)
						else:
							do_request(temp2.scheme+"://"+temp2.netloc+j)
						
						progress.advance(test_task)
		else:
			# 静默模式处理
			for i in allurls:
				for j in allurls[i]:
					output.print_url(j, i)
					temp1 = urlparse(j)
					temp2 = urlparse(url)
					
					if temp1.netloc != urlparse("1").netloc:
						do_request(j)
					else:
						do_request(temp2.scheme+"://"+temp2.netloc+j)
	else:
		output.print_warning("⚠️ No API endpoints discovered in the scanned content")
	
	# 更新统计信息
	output.stats["total_urls"] = total_urls



# 设置一个主函数，方便后续添加新的功能
def main():
	"""主函数"""
	
	# 首先处理更新检查
	if arg.update:
		with Status("[bold blue]🔄 Checking for updates...", console=output.console):
			UpdateManager.check_for_updates(force_update=True)
		sys.exit(0)
	else:
		with Status("[bold blue]🔄 Checking for updates...", console=output.console):
			UpdateManager.check_for_updates(force_update=False)

	if not arg.silent:
		show_logo()
	
	try:
		url = arg.url
		
		# 显示代理模式
		output.print_proxy_mode(do_proxys())

		# 开始扫描
		output.print_info(f"🚀 [bold green]Starting API endpoint scan...[/bold green]")
		results = find_by_url(url)
		
		if not output.silent_mode:
			if output.stats["api_endpoints"] > 0:
				output.print_info(f"🎉 [bold green]Scan completed! Found {output.stats['api_endpoints']} API endpoints.[/bold green]")
			else:
				output.print_info(f"✅ [bold yellow]Scan completed. No API endpoints found.[/bold yellow]")
	
	except KeyboardInterrupt:
		output.print_warning("\n⚠️ Scan interrupted by user")
		sys.exit(1)
	except Exception as e:
		output.print_error(f"Error: {str(e)}")
		raise  # 让Rich的异常处理器处理
	
	finally:
		output.print_stats()
		file_output.save_results(arg.url, arg)

if __name__ == '__main__':
	main()
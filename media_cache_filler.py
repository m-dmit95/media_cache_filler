#!/usr/bin/python3

import gzip
import json
import os
import shutil
import subprocess
from urllib.parse import unquote

VIEWS_INFO_FILE = '/usr/local/sibset/macrodc_cache_v5/info/views.json'
MIN_VIEWS_FOR_CACHING = 2
CACHE_PATHS = (
    '/cache/top/',
    '/cache2/top/',
    '/cache3/top/',
    '/cache4/top/',
)
# NGINX_LOG = "/var/log/nginx/access.log.3.gz"
# NGINX_LOG = "/var/log/nginx/access.log.2.gz"
# NGINX_LOG = "/var/log/nginx/access.log.1.gz"
NGINX_LOG = "/var/log/nginx/access.log"


class File:
    def __init__(self, full_path, path_prefix, cached, views):
        self.full_path = full_path
        self.path_prefix = path_prefix
        self.cached = cached
        self.views = views

        self.relative_path = self.full_path.replace(path_prefix, '')
        self.size = os.path.getsize(full_path)

    def add_views(self, new_views):
        self.views += new_views
        return new_views

    def copy_to_cache(self, cache_path_prefix):
        """Копируем файлы на кэш"""
        if self.cached is False:
            print(f'Copying file to {cache_path_prefix}: {self.full_path}')
            source = self.full_path
            destination = cache_path_prefix + self.relative_path
            destination_dir = destination.replace(
                destination.split('/')[-1],
                ''
            )
            if not os.path.exists(destination_dir):
                os.makedirs(destination_dir)
            shutil.copyfile(source, destination)
            self.path_prefix = cache_path_prefix
            self.cached = True
            return True
            '''
            TODO - сделать try except для not enough space on disk:
            OSError: [Errno 28] No space left on device
            '''
        return False

    def delete_from_cache(self):
        """Удаляем файл из кэша"""
        # Защита от дурака - нельзя удалять файл из основного хранилища
        if self.path_prefix == '/films1/share':
            print(
                f'Error while deleting {self.full_path} - ' +
                'You cannot delete file from main storage "/films1/share"!'
            )
            return False
        if self.cached is True:
            os.remove(self.full_path)
            self.cached = False
            # TODO - сделать try except если файла нет
            return True
        return False


class Cache:
    def __init__(self, path):
        self.path = path

    def get_free_space(self):
        """Возвращает объем свободного места в байтах (bytes)"""
        free_space = shutil.disk_usage(self.path)[2]
        return free_space

    def get_cached_files(self):
        """Получаем файлы, которые находятся в кэше"""
        '''ищем файлы в кэше и формируем список файлов'''
        find_files = subprocess.run(
            f'find {self.path} -type f',
            stdout=subprocess.PIPE,
            encoding='UTF-8',
            shell=True
        )
        file_list = find_files.stdout.split('\n')
        '''удаляем последний пустой элемент из списка'''
        file_list.pop()
        cached_files = {}  # {'относительный_путь_к_файлу': объект_файла}
        for path in file_list:
            file = File(
                full_path=path,
                path_prefix=self.path,
                cached=True,
                views=0
            )
            cached_files[file.relative_path] = file
        return cached_files


def get_today_top_files_and_views(logfile):
    """Сканируем access.log и берем самые популярные файлы"""
    views_count = {}
    if os.path.exists(logfile):
        if ".gz" in logfile:
            log = gzip.open(logfile, 'rt')
        else:
            log = open(logfile, 'rt')

        for line in log:
            if line.find(' 200 ') != -1:
                '''декодируем URL для кириллицы'''
                if "\\x" not in line:
                    try:
                        ip = line.split()[0]
                        path = unquote(line.split('GET ')[1].split('HTTP')[0].strip())[1:]  # noqa
                    except:  # noqa
                        continue
                else:
                    try:
                        ip = line.split()[0]
                        path = line.split('GET ')[1].split('HTTP')[0].strip().decode('unicode-escape').encode('latin1')[1:]  # noqa
                    except:  # noqa
                        print('fail')
                        continue
                if not views_count.get(path):
                    views_count[path] = [1, [ip]]
                else:
                    if not views_count[path][1].count(ip):
                        views_count[path][0] += 1
                        views_count[path][1].append(ip)
        log.close()
    else:
        print("Nginx log not exists")

    today_top = {}  # {'относительный_путь_к_файлу': объект_файла}
    for path, views in views_count.items():
        views = views[0]
        if views >= MIN_VIEWS_FOR_CACHING:
            file = File(
                full_path=f'/films1/share/{path}',
                path_prefix='/films1/share/',
                cached=False,
                views=views
            )
            today_top[file.relative_path] = file
    return today_top


def get_views_info(all_cached_files):
    """Получаем словарь {"относительный_путь": количество_просмотров}"""
    if os.path.exists(VIEWS_INFO_FILE):
        with open(VIEWS_INFO_FILE, 'r') as f:
            files_and_views = json.load(f)
    else:
        '''
        Если json не существует - cчитаем что у всех файлов 0 просмотров,
        сохраняем файл
        '''
        files_and_views = {}
        for relative_path in all_cached_files.keys():
            files_and_views[relative_path] = 0
        with open(VIEWS_INFO_FILE, 'w') as f:
            json.dump(files_and_views, f, ensure_ascii=False)
    f.close()
    return files_and_views


def save_views_info(views_info):
    with open(VIEWS_INFO_FILE, 'w') as f:
        json.dump(views_info, f, ensure_ascii=False)
    f.close()


def main():
    cache_objects = []      # Список объектов кэшей
    '''Формируем список всех файлов в кэшах'''
    all_cached_files = {}  # {'относительный_путь_к_файлу': объект_файла}
    for cache_path in CACHE_PATHS:
        '''Создаем объект для каждого кэша'''
        cache = Cache(cache_path)
        cache_objects.append(cache)
        '''Создаем список файлов, которые есть на всех кэшах'''
        cached_files = cache.get_cached_files()
        for relative_path, file in cached_files.items():
            all_cached_files[relative_path] = file
        print(f'cached_files on {cache.path}: {len(cached_files)}')
    print(f'all cached files: {len(all_cached_files)}')

    '''Получаем сегодняшний топ файлов'''
    today_top = get_today_top_files_and_views(NGINX_LOG)
    print(f'today top files: {len(today_top)}')

    '''Удаляем уже закешированные файлы из топа'''
    for relative_path in list(today_top.keys()):
        if relative_path in list(all_cached_files.keys()):
            '''Если файл уже закеширован - добавляем к нему новые просмотры'''
            new_views = today_top[relative_path].views
            all_cached_files[relative_path].add_views(new_views)
            '''Удаляем уже закешированный файл из топа'''
            del today_top[relative_path]
    print(f'files for caching: {len(today_top)}')

    '''Загружаем информацию о просмотрах каждого закешированного файла'''
    views_info = get_views_info(all_cached_files)
    '''Обновляем информацию о просмотрах в каждом объекте файла'''
    for relative_path, views in views_info.items():
        try:
            all_cached_files[relative_path].add_views(views)
        except KeyError:
            print(f'Warning - file "{relative_path}" from views.json doesnt exists on cache')  # noqa
            print('    Perhaps the previous run of the script did not finish as expected')  # noqa
            print('    or the file was deleted from the cache in another way...')  # noqa

    '''
    Создаем список закешированных ранее файлов,
    отсортированный по убыванию просмотров
    '''
    old_cached_files_sorted = sorted(
        views_info,
        key=views_info.get,
        reverse=True
    )

    '''Копируем файлы на кэш'''
    print('Start copying new files')
    for relative_path in list(today_top.keys()):
        caching_file = today_top[relative_path]
        file_copied_to_cache = False
        '''Ищем свободный кэш для нового файла'''
        while file_copied_to_cache is False:
            '''Если на каком-либо из кэшей есть место для файла - копируем'''
            for cache in cache_objects:
                if cache.get_free_space() > caching_file.size:
                    caching_file.copy_to_cache(cache.path)
                    del today_top[relative_path]
                    all_cached_files[relative_path] = caching_file
                    file_copied_to_cache = True
                    break
            if file_copied_to_cache:
                break
            '''
            Если для файла нет места на каждом кэше -
            удаляем самый непопулярный файл из старых файлов
            и повторяем поиск заного
            '''
            deleting_file_relative_path = old_cached_files_sorted.pop()
            deleting_file = all_cached_files[deleting_file_relative_path]
            deleting_file.delete_from_cache()
            del all_cached_files[deleting_file_relative_path]
            print(f'deleting {caching_file.full_path}')

    '''Сохраняем новую статистику о просмотрах закешированных файлов'''
    views_info = {}
    for file in all_cached_files.values():
        views_info[file.relative_path] = file.views
    save_views_info(views_info)
    print(len(today_top))
    print('Done!')


main()

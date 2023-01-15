#! /usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import time
import random
import requests, pickle
import json
import re
from datetime import datetime

cache_dir = 'cache'
session_cache = '%s/session.txt' % (cache_dir)
followers_cache = '%s/followers.json' % (cache_dir)
following_cache = '%s/following.json' % (cache_dir)

instagram_url = 'https://www.instagram.com'
login_route = '%s/accounts/login/ajax/' % (instagram_url)
profile_route = '%s/api/v1/users/web_profile_info/' % (instagram_url)
followers_route = '%s/api/v1/friendships/%s/followers/'
following_route = '%s/api/v1/friendships/%s/following/'
unfollow_route = '%s/web/friendships/%s/unfollow/'
session = requests.Session()


class Credentials:
    def __init__(self):
        if os.environ.get('INSTA_USERNAME') and os.environ.get('INSTA_PASSWORD'):
            self.username = os.environ.get('INSTA_USERNAME')
            self.password = os.environ.get('INSTA_PASSWORD')
        elif len(sys.argv) > 1:
            self.username = sys.argv[1]
            self.password = sys.argv[2]
        else:
            sys.exit(
                'Please provide INSTA_USERNAME and INSTA_PASSWORD environement variables or as an argument as such: ./insta-unfollower.py USERNAME PASSWORD.\nAborting...')


credentials = Credentials()


def init():
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36')
    }

    res1 = session.get(instagram_url, headers=headers)
    ig_app_id = re.findall(r'X-IG-App-ID":"(.*?)"', res1.text)[0]

    res2 = session.get('https://www.instagram.com/data/shared_data/', headers=headers, cookies=res1.cookies)
    csrf = res2.json()['config']['csrf_token']
    if csrf:
        headers['x-csrftoken'] = csrf
        # extra needed headers
        headers['accept-language'] = "en-GB,en-US;q=0.9,en;q=0.8,fr;q=0.7,es;q=0.6,es-MX;q=0.5,es-ES;q=0.4"
        headers['x-requested-with'] = "XMLHttpRequest"
        headers['accept'] = "*/*"
        headers['referer'] = "https://www.instagram.com/"
        headers['x-ig-app-id'] = ig_app_id
        ###
        cookies = res1.cookies.get_dict()
        cookies['csrftoken'] = csrf
    else:
        print("No csrf token found in code or empty, maybe you are temp ban? Wait 1 hour and retry")
        return False

    time.sleep(random.randint(2, 6))

    return headers, cookies


def login(headers, cookies):
    post_data = {
        'username': credentials.username,
        'enc_password': '#PWD_INSTAGRAM_BROWSER:0:{}:{}'.format(int(datetime.now().timestamp()), credentials.password)
    }

    response = session.post(login_route, headers=headers, data=post_data, cookies=cookies, allow_redirects=True)
    response_data = json.loads(response.text)

    if 'two_factor_required' in response_data:
        print('Please disable 2-factor authentication to login.')
        sys.exit(1)

    if 'message' in response_data and response_data['message'] == 'checkpoint_required':
        print('Please check Instagram app for a security confirmation that it is you trying to login.')
        sys.exit(1)

    return response_data['authenticated'], response.cookies.get_dict()


# Note: this endpoint results are not getting updated directly after unfollowing someone
def get_user_profile(username, headers):
    response = session.get(profile_route, params={'username': username}, headers=headers).json()
    return response['data']['user']


def get_followers_list(user_id, headers):
    followers_list = []

    response = session.get(followers_route % (instagram_url, user_id), headers=headers).json()
    while response['status'] != 'ok':
        time.sleep(600)  # querying too much, sleeping a bit before querying again
        response = session.get(followers_route % (instagram_url, user_id), headers=headers).json()

    print('.', end='', flush=True)

    followers_list.extend(response['users'])

    while 'next_max_id' in response:
        time.sleep(2)

        response = session.get(followers_route % (instagram_url, user_id), params={'max_id': response['next_max_id']},
                               headers=headers).json()
        while response['status'] != 'ok':
            time.sleep(600)  # querying too much, sleeping a bit before querying again
            response = session.get(followers_route % (instagram_url, user_id),
                                   params={'max_id': response['next_max_id']}, headers=headers).json()

        print('.', end='', flush=True)

        followers_list.extend(response['users'])

    return followers_list


def get_following_list(user_id, headers):
    follows_list = []

    response = session.get(following_route % (instagram_url, user_id), headers=headers).json()
    while response['status'] != 'ok':
        time.sleep(600)  # querying too much, sleeping a bit before querying again
        response = session.get(following_route % (instagram_url, user_id), headers=headers).json()

    print('.', end='', flush=True)

    follows_list.extend(response['users'])

    while 'next_max_id' in response:
        time.sleep(2)

        response = session.get(following_route % (instagram_url, user_id), params={'max_id': response['next_max_id']},
                               headers=headers).json()
        while response['status'] != 'ok':
            time.sleep(600)  # querying too much, sleeping a bit before querying again
            response = session.get(following_route % (instagram_url, user_id),
                                   params={'max_id': response['next_max_id']}, headers=headers).json()

        print('.', end='', flush=True)

        follows_list.extend(response['users'])

    return follows_list


# TODO: check with the new API
def unfollow(user, headers):
    if os.environ.get('DRY_RUN'):
        return True

    response = session.get(profile_route, params={'username': user['username']}, headers=headers).headers

    time.sleep(random.randint(2, 4))

    csrf = re.search(r"csrftoken=(.*?);", str(response)).group(1)

    if csrf:
        session.headers.update({'x-csrftoken': csrf})

    response = session.post(unfollow_route % (instagram_url, user['pk']))

    if response.status_code == 429:  # Too many requests
        print('Temporary ban from Instagram. Grab a coffee watch a TV show and comeback later. I will try again...')
        return False

    response = json.loads(response.text)

    if response['status'] != 'ok':
        print('Error while trying to unfollow {}. Retrying in a bit...'.format(user['username']))
        print('ERROR: {}'.format(response.text))
        return False
    return True


def main():
    if os.environ.get('DRY_RUN'):
        print('DRY RUN MODE, script will not unfollow users!')

    if not os.path.isdir(cache_dir):
        os.makedirs(cache_dir)

    headers, cookies = init()

    if os.path.isfile(session_cache):
        with open(session_cache, 'rb') as f:
            session.cookies.update(pickle.load(f))
    else:
        is_logged, cookies = login(headers, cookies)
        if is_logged == False:
            sys.exit('login failed, verify user/password combination')

        with open(session_cache, 'wb') as f:
            pickle.dump(session.cookies, f)

        time.sleep(random.randint(2, 4))

    connected_user = get_user_profile(credentials.username, headers)

    print('You\'re now logged as {} ({} followers, {} following)'.format(connected_user['username'],
                                                                         connected_user['edge_followed_by']['count'],
                                                                         connected_user['edge_follow']['count']))

    time.sleep(random.randint(2, 4))

    following_list = []
    if os.path.isfile(following_cache):
        with open(following_cache, 'r') as f:
            following_list = json.load(f)
            print('following list loaded from cache file')

    if len(following_list) != connected_user['edge_follow']['count']:
        if len(following_list) > 0:
            print('rebuilding following list...', end='', flush=True)
        else:
            print('building following list...', end='', flush=True)
        following_list = get_following_list(connected_user['id'], headers)
        print(' done')

        with open(following_cache, 'w') as f:
            json.dump(following_list, f)

    followers_list = []
    if os.path.isfile(followers_cache):
        with open(followers_cache, 'r') as f:
            followers_list = json.load(f)
            print('followers list loaded from cache file')

    if len(followers_list) != connected_user['edge_followed_by']['count']:
        if len(following_list) > 0:
            print('rebuilding followers list...', end='', flush=True)
        else:
            print('building followers list...', end='', flush=True)
        followers_list = get_followers_list(connected_user['id'], headers)
        print(' done')

        with open(followers_cache, 'w') as f:
            json.dump(followers_list, f)

    followers_usernames = {user['username'] for user in followers_list}
    unfollow_users_list = [user for user in following_list if user['username'] not in followers_usernames]

    print('you are following {} user(s) who aren\'t following you:'.format(len(unfollow_users_list)))
    for user in unfollow_users_list:
        print(user['username'])

    if len(unfollow_users_list) > 0:
        print('Begin to unfollow users...')

        for user in unfollow_users_list:
            if not os.environ.get('UNFOLLOW_VERIFIED') and user['is_verified'] == True:
                print('Skipping {}...'.format(user['username']))
                continue

            time.sleep(random.randint(5, 10))

            print('Unfollowing {}...'.format(user['username']))
            while unfollow(user, headers) == False:
                sleep_time = random.randint(1, 3) * 1000  # High number on purpose
                print('Sleeping for {} seconds'.format(sleep_time))
                time.sleep(sleep_time)

        print(' done')


if __name__ == "__main__":
    main()

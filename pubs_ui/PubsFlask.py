import sys
import json
from flask import render_template, abort, request, Response, jsonify, url_for, redirect
from flask_mail import Message
from requests import get
from webargs.flaskparser import FlaskParser
from flask.ext.paginate import Pagination
from arguments import search_args
from utils import (pubdetails, pull_feed, create_display_links, getbrowsecontent,
                   SearchPublications, contributor_lists, jsonify_geojson)
from forms import ContactForm, SearchForm
from canned_text import EMAIL_RESPONSE
from pubs_ui import app, mail

#set UTF-8 to be default throughout app
reload(sys)
sys.setdefaultencoding("utf-8")


pub_url = app.config['PUB_URL']
lookup_url = app.config['LOOKUP_URL']
supersedes_url = app.config['SUPERSEDES_URL']
browse_url = app.config['BROWSE_URL']
search_url = app.config['BASE_SEARCH_URL']
citation_url = app.config['BASE_CITATION_URL']
browse_replace = app.config['BROWSE_REPLACE']
contact_recipients = app.config['CONTACT_RECIPIENTS']


#should requests verify the certificates for ssl connections
verify_cert = app.config['VERIFY_CERT']


@app.route('/')
def index():
    sp = SearchPublications(search_url)
    recent_publications_resp = sp.get_pubs_search_results(params={'pubs_x_days': 7, 'page_size': 6}) # bring back recent publications
    recent_pubs_content = recent_publications_resp[0]
    try:
        pubs_records = recent_pubs_content['records']
    except TypeError:
        pubs_records = [] # return an empty list recent_pubs_content is None (e.g. the service is down)
    form = SearchForm(None, obj=request.args)
    return render_template('home.html',
                           recent_publications=pubs_records, 
                           form=form
                           )


#contact form
@app.route('/contact', methods=['GET', 'POST'])
def contact():
    contact_form = ContactForm()
    if request.method == 'POST':
        if contact_form.validate_on_submit():
            human_name = contact_form.name.data
            human_email = contact_form.email.data
            if human_name:
                sender_str = '({name}, {email})'.format(name=human_name, email=human_email)
            else:
                sender_str = '({email})'.format(email=human_email)
            subject_line = 'Pubs Warehouse User Comments' # this is want Remedy filters on to determine if an email goes to the pubs support group
            message_body = contact_form.message.data
            message_content = EMAIL_RESPONSE.format(contact_str=sender_str, message_body=message_body)
            msg = Message(subject=subject_line,
                          sender=(human_name, human_email),
                          reply_to=('PUBSV2_NO_REPLY', 'pubsv2_no_reply@usgs.gov'), # this is not what Remedy filters on to determine if a message goes to the pubs support group...
                          recipients=contact_recipients, # will go to servicedesk@usgs.gov if application has DEBUG = False
                          body=message_content
                          )
            mail.send(msg)            
            return redirect(url_for('contact_confirmation')) # redirect to a confirmation page after successful validation and message sending
        else:
            return render_template('contact.html', contact_form=contact_form) # redisplay the form with errors if validation fails
    elif request.method == 'GET':
        return render_template('contact.html', contact_form=contact_form)

    
@app.route('/contact_confirm')
def contact_confirmation():
    confirmation_message = 'Thank you for contacting the USGS Publications Warehouse support team.'
    return render_template('contact_confirm.html', confirm_message=confirmation_message)


#leads to rendered html for publication page
@app.route('/publication/<indexId>')
def publication(indexId):
    r = get(pub_url+'publication/'+indexId, params={'mimetype': 'json'}, verify=verify_cert)
    pubreturn = r.json()
    pubdata = pubdetails(pubreturn)
    pubdata = create_display_links(pubdata)
    pubdata = contributor_lists(pubdata)
    img_source = pubdata['displayLinks']['Thumbnail'][0]['url']
    pubdata = jsonify_geojson(pubdata)
    if 'mimetype' in request.args and request.args.get("mimetype") == 'json':
        return jsonify(pubdata)
    else:
        return render_template('publication.html', indexID=indexId, pubdata=pubdata, img_source=img_source)


#leads to json for selected endpoints
@app.route('/lookup/<endpoint>')
def lookup(endpoint):
    endpoint_list = ['costcenters', 'publicationtypes', 'publicationsubtypes', 'publicationseries']
    endpoint = endpoint.lower()
    if endpoint in endpoint_list:
        r = get(lookup_url+endpoint, params={'mimetype': 'json'},  verify=verify_cert).json()
        return Response(json.dumps(r),  mimetype='application/json')
    else:
        abort(404)


@app.route('/documentation/faq')
def faq():
    feed_url = 'https://my.usgs.gov/confluence/createrssfeed.action?types=page&spaces=pubswarehouseinfo&title=myUSGS+4.0+RSS+Feed&labelString=pw_faq&excludedSpaceKeys%3D&sort=modified&maxResults=10&timeSpan=600&showContent=true&confirm=Create+RSS+Feed'
    return render_template('faq.html', faq_content=pull_feed(feed_url))


@app.route('/documentation/usgs_series')
def usgs_series():
    feed_url = 'https://my.usgs.gov/confluence/createrssfeed.action?types=page&spaces=pubswarehouseinfo&title=myUSGS+4.0+RSS+Feed&labelString=usgs_series&excludedSpaceKeys%3D&sort=modified&maxResults=10&timeSpan=3600&showContent=true&confirm=Create+RSS+Feed'
    return render_template('usgs_series.html', usgs_series_content=pull_feed(feed_url))


@app.route('/documentation/web_service_documentation')
def web_service_docs():
    feed_url = 'https://my.usgs.gov/confluence/createrssfeed.action?types=page&spaces=pubswarehouseinfo&title=myUSGS+4.0+RSS+Feed&labelString=pubs_webservice_docs&excludedSpaceKeys%3D&sort=modified&maxResults=10&timeSpan=3650&showContent=true&confirm=Create+RSS+Feed'
    return render_template('webservice_docs.html', web_service_docs=pull_feed(feed_url))


@app.route('/documentation/other_resources')
def other_resources():
    feed_url = 'https://my.usgs.gov/confluence/createrssfeed.action?types=page&spaces=pubswarehouseinfo&title=myUSGS+4.0+RSS+Feed&labelString=other_resources&excludedSpaceKeys%3D&sort=modified&maxResults=10&timeSpan=3650&showContent=true&confirm=Create+RSS+Feed'
    return render_template('other_resources.html', other_resources=pull_feed(feed_url))


@app.route('/browse/', defaults={'path': ''})
@app.route('/browse/<path:path>')
def browse(path):
    app.logger.info("path: "+path)
    browsecontent = getbrowsecontent(browse_url+path, browse_replace)
    return render_template('browse.html', browsecontent=browsecontent)


#this takes advantage of the webargs package, which allows for multiple parameter entries. e.g. year=1981&year=1976
@app.route('/search', methods=['GET'])
def api_webargs():
    parser = FlaskParser()
    search_kwargs = parser.parse(search_args, request)
    form = SearchForm(None, obj=request.args)
    per_page = 15
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    search_kwargs['page_size'] = per_page
    search_kwargs['page_number'] = page
    sp = SearchPublications(search_url)
    search_results, resp_status_code = sp.get_pubs_search_results(params=search_kwargs) # go out to the pubs API and get the search results
    try:
        search_result_records = search_results['records']
        record_count = search_results['recordCount']
        pagination = Pagination(page=page, total=record_count, per_page=per_page, record_name='Search Results')
        search_service_down = None
    except TypeError:
        search_result_records = None
        pagination = None
        search_service_down = 'The backend services appear to be down with a {0} status.'.format(resp_status_code)
    return render_template('search_results.html', 
                           search_result_records=search_result_records,
                           pagination=pagination,
                           search_service_down=search_service_down,
                           form=form
                           )

    # print 'webarg param: ', search_kwargs
    #TODO: map the webargs to the Pubs Warehouse Java API, generate output
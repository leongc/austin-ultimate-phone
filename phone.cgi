#!/usr/bin/perl

# Mostly written August 2000 by Cheng Leong
# read_net_input and urldecode adapted from kmeltz@cris.com upload.pl
#
# This multi-function script is designed to manage a web-interfaced
# semi-public phone book.  The different functions are accessed
# by appropriate use of GET or POST methods and the SUBMIT field.
#
# If the script is invoked using GET...
# ...and ID is specified then a listing is shown.
# ...and target is specified then an error, list, or single listing is shown
# ...the DEFAULT is to list all public records
#
# If the script is invoked using POST...
# ...and submit = "Add" (DEFAULT) then a new record is added.
#
# Add expects the following input fields: 
#   first, last, nick, phone, email, address1, address2,
#   city, state, zip, list, notes
#   list is one of: "full", "search", "paper", "hermit"
#
# Search expects the following input field:
#   target
# 3 or less characters will return only exact matches on 
# first name, nickname, or last name.
# 4 or more characters will return substring matches on 
# first name, nickname, and last name.
#
# Lazy-write cache for public listings and individual listings.
# Caching strategy: maximal laziness; generate cache file only when required.
# For public listings, compare db timestamp and cache timestamp.
# Generate it if cache is old, use it if cache is current.
# For individual listings, use it if it exists, or generate it.
# Warning: manual edit of db will not mark individual caches dirty
#

# The information is stored in a text database specified by $audbname
# the database is defined by $fieldsep, $recordsep, and @aufieldnames

# TODO:
#
# If the script is invoked using GET...
# ...and submit = "ShowAdd" then show a form to add a new record 
# ...and submit = "ShowEdit" then show a form to edit record specified by ID 
# ...and submit = "Remove" then remove record specified by ID

# If the script is invoked using POST...
# ...and submit = "Update" then update specified record
#
#

# History:
# 	2000.08.03 cwl	Script created. Append_record implemented.
#			Simple db datastructure load.
#	2000.08.04 cwl	show_online, show_single implemented.
#			db_load simplified.
#	2000.08.05 cwl	search_for implemented, show_multiple extracted from
#			show_online
#	2000.08.05 cwl	lazy-write caching implemented; show_single and
#			show_online affected, show_multiple => HTML_multiple
#	2000.08.10 cwl	bug-fix sort on unique key: first.last.id not just first

#### Global variables ####

$webmaster = $ENV{'SERVER_ADMIN'};
# $authorurl = 'leongc@alumni.rice.edu';
$ENV{'SERVER_URL'} = "http://$ENV{'HTTP_HOST'}" unless $ENV{'SERVER_URL'};
$thisurl = $ENV{'SERVER_URL'}.$ENV{'SCRIPT_NAME'};
$tempdb = '/tmp/db.'.time().'.tmp';	# writable scratch area
$fieldsep = "\n";
$recordsep = "-----8<-----\n";
$audbname = '/usr/home/httpd/phonebook/austin-ultimate.db'; # recommend absolute path not in html doc tree
$aucachedir = '/usr/home/httpd/phonebook/cache'; # must have read-write access
#$aucachedir = '/tmp/cache'; # must have read-write access
$aucachefile = "$aucachedir/austin-ultimate_public.htmlf"; # for public list
@aufieldnames = qw( ID
		    first
		    last
		    nick
		    address1
		    address2
		    city
		    state
		    zip
		    phone
		    email
		    list
		    notes );
@ausearchfields = qw ( first last nick ); # fields for searching
# availability of listing from public to private
@aulistvalues = qw( full
		    search
		    paper
		    hermit );

$htmlheader = '/usr/home/httpd/html/header.html';
$htmlfooter = '/usr/home/httpd/html/footer.html';

$printedheader = 0;

#### MAIN ####
main();

sub main {
    read_net_input();

    print_header();
#    show_test_output(); # DEBUG
    
    if ( $GLOBAL{'target'} ) {
	# search for target matches
	search_for($GLOBAL{'target'});
    } elsif ( $GLOBAL{'ID'} ) { # && $ENV{'REQUEST_METHOD'} eq 'GET'
	# attempt to show single listing
	show_single( $GLOBAL{'ID'} );
    } elsif ( $ENV{'REQUEST_METHOD'} eq 'POST' ) {
	# if ( $GLOBAL{'submit'} eq 'Add' ) {
 	    # append submitted info to db
	    append_record($audbname, @aufieldnames);
	# }
    } else { # DEFAULT
        # show all online listings
	show_online();
    }

    print_footer();

    1;
} # end of main


#### Output subroutines ####

sub print_header {
    return if ($printedheader > 0);
    print "Content-Type: text/html\n\n";
    if ( open(HH, "<$htmlheader") ) { 
	while ( <HH> ) { print; }
	close(HH);
    }
    $printedheader++;
    1;
} # end of print_header 

sub print_footer {
    if ( open(HF, "<$htmlfooter") ) {
	while ( <HF> ) { print; }
	close(HF);
    }
    1;
} # end of print_footer

sub show_test_output {
    while( ($n, $v) = each(%ENV)) { print "$n = $v <br>"; } print "<br>"; 
    while( ($n, $v) = each(%GLOBAL)) { print "$n = $v <br>"; } print "<br>"; 

    1;
} # end of show_test_output

sub show_append_success {
    local($id) = @_;

    print "<h2>Successfully Added!</h2>\n";
    show_single($id);

    1;
} # end show_append_success

# returns a HTML-display safe version of the input
sub html_safe {
    local ($i) = @_;

    $i =~ s/&/&amp;/g;
    $i =~ s/>/&gt;/g;
    $i =~ s/</&lt;/g;
    return $i;
} # end html_safe


# prints an HTML table of records
sub show_online {
    local ($id, %people, $rrecord, %resultset, @resultlist);

    show_searchform();
    print "<hr>\n";
    print "<h2>Public Address Listings</h2>\n";

    # show cached version if it exists and is fresher than the DB
    if ((-e $aucachefile) && 
	(-M $aucachefile < -M $audbname) && # -M = age of file relative to now
	(open(CACHE, "<$aucachefile"))) {
	while ( <CACHE> ) { print; }
	close(CACHE);
    } else {
	# generate result and cache it
	%people = %{ load_db($audbname, @aufieldnames) };

	# select only authorized records
	# save keys in %resultset keyed on name so it can be sorted
	while ( ($id, $rrecord) = each(%people) ) { 
	    local ($sortkey);
#	    print "$id = %{$rrecord}<br>\n"; 	# DEBUG

	    next if ($rrecord->{'list'} ne 'full');  # only show 'full' records
	    $sortkey = $rrecord->{'first'} . $rrecord->{'last'} . $id; # sort on first.last.id
	    $resultset{$sortkey} = $id;
	}

	# build array of IDs
	foreach my $person (sort { uc($a) cmp uc($b) } (keys %resultset)) {
	    push @resultlist, $resultset{$person};
	}
	
	$rawhtml = HTML_multiple(\%people, @resultlist); # cache this result

        if (open(CACHE, ">$aucachefile")) {
	    print CACHE $rawhtml;
	    close(CACHE);
	} else {
	    print <<ENDWARNING;
<hr>
Warning: cache is broken. Please notify the webmaster
(<a href="mailto:$webmaster?SUBJECT=Broken+cache+$thisurl+$aucachefile">$webmaster</a>)
ENDWARNING

        } # end attempt to write to cache
        print $rawhtml;

    } # end else no cache

    1;
} # end of show_online

# returns HTML for a table containing multiple a-u entries
# using data from %{$rdb} as specified by @idlist
sub HTML_multiple {
    local($rdb, @idlist) = @_;
    local($entry, $rawhtml);

    $rawhtml = <<ENDTABLEHEAD;
    <table width="100%" cellpadding="1" cellspacing="0"> <!-- 3 col table -->
      <tr><th width="50%"></th><th width="25%"></th><th width="25%"></th></tr>
ENDTABLEHEAD

    while ($entry = shift @idlist) {
	local ($nickhtml, $firsthtml, 
	       $lasthtml, $emailhtml, $phonehtml, $noteshtml);

	$firsthtml = html_safe($rdb->{$entry}->{'first'});
	$nickhtml = '"' . html_safe($rdb->{$entry}->{'nick'}) . '"' 
	    if $rdb->{$entry}->{'nick'};
	$lasthtml = html_safe($rdb->{$entry}->{'last'});
	$emailhtml = html_safe($rdb->{$entry}->{'email'});
	$phonehtml = html_safe($rdb->{$entry}->{'phone'});
	$noteshtml = 'Notes: ' . html_safe($rdb->{$entry}->{'notes'}) 
	    if $rdb->{$entry}->{'notes'};
	$rawhtml .= <<ENDRECORD;
      <tr>
	<td><a href="$thisurl?ID=$entry">
	    $firsthtml $nickhtml $lasthtml</a></td>
	<td><a href="mailto:$emailhtml">$emailhtml</a></td>
	<td>$phonehtml</td>
      </tr><tr>
	<td colspan="3">$noteshtml<br><hr height="1"></td>
      </tr>
ENDRECORD

    }

    $rawhtml .= "    </table> <!-- end 3 col table -->\n";
    return $rawhtml;

} # end of HTML_multiple

# list a single record identified by $id
sub show_single {
    local ($id) = @_;
    local ($cachefile, %people, $rrecord);

    # show cached version if it exists
    $cachefile = "$aucachedir/$id.htmlf";
    if ((-e $cachefile) && 
	(open(CACHE, "<$cachefile"))) {
	while ( <CACHE> ) { print; }
	close(CACHE);
    } else {
	# generate cache file
	%people = %{ load_db($audbname, @aufieldnames) };

	($rrecord = $people{$id}) || exit_search_failure("ID $id unknown");

	local($firsthtml, $nickhtml, $lasthtml, $emailhtml, $phonehtml,
	      $address1html, $address2html, $cityhtml, $statehtml, $ziphtml,
	      $noteshtml, $rawhtml);
	
	# ensure DB content is safe for display
	$firsthtml = html_safe($rrecord->{'first'});
	$nickhtml = html_safe($rrecord->{'nick'});
	$lasthtml = html_safe($rrecord->{'last'});
	$emailhtml = html_safe($rrecord->{'email'});
	$phonehtml = html_safe($rrecord->{'phone'});
	$address1html = html_safe($rrecord->{'address1'});
	$address2html = html_safe($rrecord->{'address2'});
	$cityhtml = html_safe($rrecord->{'city'});
	$statehtml = html_safe($rrecord->{'state'});
	$ziphtml = html_safe($rrecord->{'zip'});
	$noteshtml = html_safe($rrecord->{'notes'});
	# defaults
	$cityhtml = 'Austin' unless $cityhtml;
	$statehtml = 'TX' unless $statehtml;
	# conditional display
	$nickhtml = "\"$nickhtml\"" if $nickhtml;
	$noteshtml = "Notes: $noteshtml" if $noteshtml;

	$rawhtml = <<ENDSINGLE; # cache this result
    <h2>Player Address Listing</h2>
    <h3>$firsthtml $nickhtml $lasthtml</h3>
    <a href="mailto:$emailhtml">$emailhtml</a><br>
    $phonehtml<br>
    $address1html<br>
    $address2html<br>
    $cityhtml, $statehtml $ziphtml<br>
    $noteshtml<br>
ENDSINGLE

        if (open(CACHE, ">$cachefile")) {
	    print CACHE $rawhtml;
	    close(CACHE);
	} else {
	    print <<ENDWARNING;
<hr>
Warning: cache is broken. Please notify the webmaster
(<a href="mailto:$webmaster?SUBJECT=Broken+cache+$thisurl+$cachefile">$webmaster</a>)
ENDWARNING

        } # end attempt to write to cache
        print $rawhtml;

    } # end else no cache

    print "<hr>\n";
    show_searchform();

    1;
} # end of show_single

# HTML search form suitable for use with this script
sub show_searchform {

    print <<ENDFORM;
<FORM METHOD="GET">
<h3>Search</h3>
3 or less characters will return only exact matches on first name, nickname, or last name.<br>
4 or more characters will return substring matches on first name, nickname, and last name.<br>
<input type="TEXT" name="target" size="10" maxlength="20">
<input type="submit" name="submit" value="Search">
</FORM> <!-- end search form -->
ENDFORM

} # end of show_searchform

#### failure exit subroutines ####

sub exit_data_failure {
    local($reason) = @_;
    handle_failure("Data Entry Failed", <<ENDDATAFAIL);
The requested input is invalid.<br>
Reason : $reason.<br>
ENDDATAFAIL

} # end of exit_data_failure

sub exit_search_failure {
    local($reason) = @_;
    handle_failure("Database Search Failed", <<ENDSEARCHFAIL);
The requested record(s) could not be found in the database.<br>
Reason : $reason.<br>
ENDSEARCHFAIL

} # end of exit_search_failure

sub exit_dbread_failure {
    local($reason) = @_;
    handle_failure("Database Read Failed", <<ENDREADFAIL);
The requested database could not be found on the server.<br>
Reason : $reason. The server may have decided not let you read to the database.<br>
ENDREADFAIL

} # end of exit_dbread_failure

sub exit_dbsave_failure {
    local($reason) = @_;
    local($recordname) = $GLOBAL{'name'};
    handle_failure("Database Save Failed", <<ENDSAVEFAIL);
The requested record $recordname was not uploaded to the server.<br>
Reason : $reason. The server may have decided not let you write to the database.<br>
ENDSAVEFAIL

} # end of exit_dbsave_failure

sub handle_failure {
    local($title, $longreason) = @_;

    print <<ENDFAIL;
    <H2>$title</H2>
    $longreason<br>
    Please contact the web master (<a href="mailto:$webmaster">$webmaster</a>) for this problem.<br>
    Connection closed by foreign host.<br>
ENDFAIL

    print_footer();
    exit;  
} # end of handle_failure

#### input subroutines ####

# given a string, remove excess whitespace (intended for web input fields)
sub trim {
    local ($fat) = @_;
    return $fat unless $fat;
    $fat =~ s/^\s+//;
    $fat =~ s/\s+$//;
    return $fat;
}; # end of trim

# insert all name,value field pairs into the %GLOBAL hash
sub urldecode {
    local($in) = @_; 
    local($i, @input_list); 

    @input_list = split(/&/,$in);

    foreach $i (@input_list) {
        $i =~ s/\+/ /g;      # Convert pluses to spaces

        # Convert %XX from hex numbers to alphanumeric
        $i =~ s/%(..)/pack("c",hex($1))/ge;

        # Split into key and value.
        $loc = index($i,"=");
        $key = substr($i,0,$loc);
        $val = substr($i,$loc+1);
        $GLOBAL{$key} = $val;
    }

    1;
} # end of urldecode 

sub read_net_input {
    local ($i, $loc, $key, $val, $input);
    local($f,$header, $len, $buf); 

    if ($ENV{'REQUEST_METHOD'} eq "GET")
    { $input = $ENV{'QUERY_STRING'}; }
    elsif ($ENV{'REQUEST_METHOD'} eq "POST")
    {  
        # Need to read TILL we got all bytes
	$len = 0;
	$input = ''; 
	while( $len != $ENV{'CONTENT_LENGTH'} ) {
	    $buf = ''; 
	    $len += sysread(STDIN, $buf, $ENV{'CONTENT_LENGTH'});
	    $input .= $buf; 
	}
#	$GLOBAL{'DEBUG_INPUT'} = $input; # debugging
    }

    # conform to RFC1867 for upload specific 
    if( $ENV{'CONTENT_TYPE'} =~ /multipart\/form-data; boundary=(.+)$/ ) {
	$boundary = '--'.$1;  # please refer to RFC1867 
	@list = split(/$boundary/, $input); 

#	$GLOBAL{'DEBUG_LIST'} = join("|", @list); # debugging
	foreach $header_body (@list) {
	    # look for header containing "filename="
	    if ((! defined $GLOBAL{'FILE_CONTENT'}) 
		&& ($header_body =~ /filename=\"(.+)\"/)) {
		$GLOBAL{'FILE_NAME'} = $1; 
		$GLOBAL{'FILE_NAME'} =~ s/\"//g; # remove "s
		$GLOBAL{'FILE_NAME'} =~ s/\s//g; # make sure no space(include \n, \r..) in the file name 

		$header_body =~ /\r\n\r\n|\n\n/; # separate header and body 
		$header = $`;        # front part
		$body   = $';        # rear part
		$body =~ s/\r\n$//;  # the last \r\n was put in by Netscape
		$GLOBAL{'FILE_CONTENT'} = $body;  
	    }
	    # normal field name/value pair
	    $header_body =~ s/^.+name=$//; 
	    $header_body =~ /\"(\w+)\"/; 
	    $GLOBAL{$1} = $'; 
	}
	return 1; 
    }

    urldecode($input); 

    1;
} # end of read_net_input 


#### database access routines ####


sub load_db {
    # reads given filename and fieldorder and returns a reference to a hash
    # the key is the first field listed
    # the values are hashes keyed by fieldnames
    local ($filename, @fieldnames) = @_;
    local (%fieldorder, %database, $index, $key, $name, $value, %info);
    
    # create %fieldorder based on @fieldnames
    for (my $index = 0; $index < @fieldnames; ++$index) {
	$fieldorder{$fieldnames[$index]} = $index;
    }

    if (open(DB,"<$filename")  || exit_dbread_failure("$filename  $!")) {
	while (<DB>) {
	    if ( /$recordsep/ ) {
		my %hashcopy = %info;
		$database{$key} = \%hashcopy if $key;
		undef $key;
		undef %info;  # make new hash object for each record
	    } elsif ( /=/ ) {
		# build record in %info
		$name = $`;   # front
		$value = $';  # rear
		chomp ($value);
#		print "$name = $value<br>\n";	# DEBUG
		$index = $fieldorder{$name};
		next unless defined $index; # skip unknown fields
		$key = $value if ($index == 0);
		undef $index;
		$info{$name} = $value;
	    } else {
		next;  # ignore unknown input
	    }
	}
	$database{$key} = \%info if $key;
	close(DB); 
    }

    return \%database; # dbref

} # end of load_db

sub update_record {
    # WARNING: NOT CONVERTED, DO NOT USE YET
    local ($target, $dbname, @fieldorder) = @_;

    # write to db by reading old db, 
    # replacing old record with new info in a temp db,
    # then swapping dbs 
    if (open(DB,"<$dbname")  || exit_dbread_failure("$dbname  $!")) {
        if (open(DBOUT, ">$tempdb") || exit_dbsave_failure("$tempdb  $!")) {

	    $deletethis=0; # 0=before target
LINE:	    while (<DB>) {
		$thisline = $_;
		if (($deletethis == 0) && 
		    ($thisline =~ /^$fieldorder[0]=$target$fieldsep/)) {
		    $deletethis = 1; # 1=target record is current
		    # write updated record
		    foreach my $fieldname (@fieldorder) {
			local ($fieldval) = $GLOBAL{$fieldname}; 
			print DBOUT "$fieldname=$fieldval", $fieldsep;
		    }
		    print DBOUT $recordsep;
		    next LINE;
		}
		if ($deletethis == 1) { # 1=target record is current
		    if ($thisline eq $recordsep) {
			$deletethis = 2; # 2=past target
			# do not skip the trailing $recordsep
		    } else {
			next LINE;
		    }
		}
		print DBOUT $thisline;
	    }
	    close(DBOUT);
	}
	close(DB);
	system ('mv', '-f', $tempdb, $dbname);
	
	show_update_success();
    }
    1;
} # end of update_record

# appends record to database specified by $dbname
# record consists of fields specified by @fieldorder
# first field should be the key field
# record data is in %GLOBAL 
# 
sub append_record {
    local ($dbname, @fieldorder) = @_;
    local ($data, $key);
    
    # skip if no name data
    foreach (@ausearchfields) { $data .= $GLOBAL{$_}; }
    exit_data_failure('No searchable data provided.<br> Suggestion : at least put 
your name and another useful fact in') unless $data;

    # generate unique ID = time + ip address + port
    $key = $ENV{'REMOTE_ADDR'};
    $key =~ s/[^\d]//g;	# remove nondigits
    $key = time() . sprintf('%012u', $key) . sprintf('%05u', $ENV{'REMOTE_PORT'});
    $GLOBAL{$fieldorder[0]} = $key;

    if (open(DB, ">>$dbname") || exit_dbsave_failure("$dbname", $!)) {
	foreach my $fieldname (@fieldorder) {
	    local ($fieldval) = $GLOBAL{$fieldname}; 
	    print DB "$fieldname=$fieldval", $fieldsep;
	}
	print DB $recordsep;
	close (DB);
	show_append_success($key);
    }

    return $key;
} # end of append_record

# looks for target in @ausearchfields
# if target < 4 characters then show only exact matches
# if target >=4 characters then show substring matches
sub search_for {
    local ($target) = @_;
    local (%people, @idlist, $exact, $id, $rrecord);
    
    exit_search_failure('No target given') unless $target;
    
    $exact = (length $target < 4);
    %people = %{ load_db($audbname, @aufieldnames) };
    
PERSON:    while ( ($id, $rrecord) = each(%people) ) { 
	local ($sortkey);
#	print "$id = %{$rrecord}<br>\n"; 	# DEBUG

	# only show 'full' and 'search' records
	next unless (($rrecord->{'list'} eq 'full') ||
		     ($rrecord->{'list'} eq 'search'));
	$sortkey = $rrecord->{'first'} . $rrecord->{'last'} . $id; # sort on first.last.id

	$target = lc($target); # case-insensitive, use lowercase
	# search on specified fields for exact match || substring match
	foreach my $field (@ausearchfields) {
	    if ((lc($rrecord->{$field}) eq $target) ||
		(!$exact && (lc($rrecord->{$field}) =~ /$target/))) {
		    $resultset{$sortkey} = $id;
		    next PERSON;
		}
	}
    } # end while PERSON

    # build array of IDs
    foreach my $person (sort { uc($a) cmp uc($b) } (keys %resultset)) {
	push @idlist, $resultset{$person};
    }
    
    print "<h2>Address Listings for '$target'</h2>\n";
    if (@idlist > 1) { 
	print HTML_multiple(\%people, @idlist);
	show_searchform();
    } elsif (@idlist == 1) {
	show_single(@idlist[0]); 
    } else {
	exit_search_failure('Sorry, no listings matched your criteria');
    }
    1;
} # end of show_search_results


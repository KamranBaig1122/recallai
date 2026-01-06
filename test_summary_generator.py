"""
Test script for summary generator
Paste your transcription here to test if it generates a summary
This script only prints to console, doesn't save anything

Usage:
    python test_summary_generator.py                    # Uses TRANSCRIPT variable below
    python test_summary_generator.py --file path/to/transcript.txt
    python test_summary_generator.py --text "Your transcript text here..."
"""
import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'recallai.settings')
django.setup()

from app.services.groq.summary_generator import generate_summary_and_action_items_with_groq
import argparse


def test_summary_generation(transcript_text: str):
    """
    Test the summary generator with given transcript text
    """
    print("=" * 80)
    print("TESTING SUMMARY GENERATOR")
    print("=" * 80)
    print(f"\n📝 Transcript Length: {len(transcript_text):,} characters")
    print(f"📊 Estimated tokens: ~{len(transcript_text) // 4:,}")
    print(f"⏱️  Estimated timeout: {max(60, len(transcript_text) // 1000)} seconds")
    print("\n" + "=" * 80)
    print("CALLING GROQ API...")
    print("=" * 80 + "\n")
    
    # Call the summary generator
    result = generate_summary_and_action_items_with_groq(transcript_text)
    
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)
    
    if result is None:
        print("❌ FAILED: Summary generation returned None")
        print("\nPossible reasons:")
        print("  - GROQ_API_KEY not set or invalid")
        print("  - Transcript too short (< 10 characters)")
        print("  - API request failed (check network/timeout)")
        print("  - API response parsing failed")
        return
    
    print("\n✅ SUCCESS: Summary generated!")
    print("\n" + "-" * 80)
    print("SUMMARY:")
    print("-" * 80)
    summary = result.get('summary', '')
    if summary:
        print(summary)
        print(f"\n📏 Summary length: {len(summary):,} characters")
    else:
        print("⚠️  WARNING: Summary is empty!")
    
    print("\n" + "-" * 80)
    print("ACTION ITEMS:")
    print("-" * 80)
    action_items = result.get('action_items', [])
    if action_items:
        for i, item in enumerate(action_items, 1):
            text = item.get('text', str(item))
            print(f"\n{i}. {text}")
        print(f"\n📋 Total action items: {len(action_items)}")
    else:
        print("⚠️  WARNING: No action items found!")
    
    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


# OPTION 1: Paste your transcription directly here (EASIEST WAY)
TRANSCRIPT = """Mike Volkin
Hey, daniel.

Mike Volkin
Why is my camera not working? Hold on one second here.

Mike Volkin
Can you hear me? Okay?

Daniyal Sultan
Yes. Hi,

Mike Volkin
Paul. Hey, there. Doing good. Thanks for joining, man. Sorry I was running late today.

Daniyal Sultan
No worries. A very happy New Year

Mike Volkin
to you. Yeah, you too. Hope your holiday season went well.

Daniyal Sultan
Yeah. Holidays worked well.

Daniyal Sultan
And as I mentioned, on a trip to Dubai,

Daniyal Sultan
For some work. So it was good over there as well. The weather was good.

Daniyal Sultan
We had to had a chance to witness some of Sandstorm as well.

Daniyal Sultan
And also bunch of rays, so it was good.

Mike Volkin
Cool. That's good. Hope you got some good family time. Is anybody else from the team going to be joining us?

Daniyal Sultan
No, actually, I would be taking care of the demo itself.

Daniyal Sultan
And Ali has also joined us. I see that.

Daniyal Sultan
It would be actually taking transcription nodes and stuff.

Mike Volkin
Okay, awesome.

Daniyal Sultan
So let me just get started with it.

Mike Volkin
So Ellie is not taking visual cues, right?

Mike Volkin
Just audio at this point.

Daniyal Sultan
Yeah. At this point, only audio. So taking the transcription.

Daniyal Sultan
I would be going through about that component in the call as well.

Daniyal Sultan
So can you see my screen?

Mike Volkin
Yes.

Daniyal Sultan
So we had the design. This is like the main, what we call marketing website.

Daniyal Sultan
The landing page.

Daniyal Sultan
I will share this link with you as well so we can change any content or update any sections as we prefer.

Mike Volkin
So

Daniyal Sultan
according to design, we have implemented this. From here, we have these buttons we can use to navigate to different screens.

Daniyal Sultan
For. Let's go to sign up one over here. We have different options.

Daniyal Sultan
Like sign up with Google, or you can sign up with Microsoft.

Daniyal Sultan
Or you can sign up manually as well, using your email.

Daniyal Sultan
Let's go to the

Mike Volkin
flow.

Daniyal Sultan
It's pretty straightforward.

Daniyal Sultan
These are like our credentials from Superbase once. This is like staging environment.

Daniyal Sultan
Once we move to production, we will change these like the domain and stuff we have. Once we integrate it with that and we are ready.

Daniyal Sultan
To because we don't want any of the testing data to go into our production environment. So we have these, like, testing.

Daniyal Sultan
Set up right now.

Daniyal Sultan
For as well. The flow is pretty similar.

Daniyal Sultan
As usually we have in applications. You click on it and then you have some screens.

Daniyal Sultan
Which you can actually go through and then associate your account and use that for sign up. For manually you can add anywhere.

Daniyal Sultan
Hold on.

Mike Volkin
This

Daniyal Sultan
air

Mike Volkin
conditioner really loud. I'm going to turn off this air conditioning real quick. I'll be back in, like, 10 seconds. Okay? Sorry.

Mike Volkin
Okay, thank you very much.

Daniyal Sultan
So once you add these details and an email.

Daniyal Sultan
Or verification.

Daniyal Sultan
My email is loading.

Daniyal Sultan
Up.

Daniyal Sultan
Oh, your email is slow.

Daniyal Sultan
Ly.

Mike Volkin
Yeah.

Daniyal Sultan
Let me see if my vpn is.

Mike Volkin
Yeah. It says confirm your sign up, right?

Daniyal Sultan
And obviously update the text of this email.

Mike Volkin
Based

Daniyal Sultan
on our preference and compliance.

Daniyal Sultan
So we have.

Daniyal Sultan
Once you confirm your email, then you are routed to this screen.

Daniyal Sultan
From here, you can go to Login or open the dashboard.

Mike Volkin
Once you open this.

Mike Volkin
Sorry. It says go to login. Aren't you already logged in at this point?

Daniyal Sultan
You can use the option to go to

Mike Volkin
Dashboard.

Daniyal Sultan
And I think we can remove that.

Daniyal Sultan
Button for login and just add for go to

Mike Volkin
Okay, yeah, it says login at the top to it, but you're obviously logged in because you're updating your profile. But you see, the nav bar still says logged in.

Mike Volkin
But nonetheless, those are little things.

Daniyal Sultan
We can go through later. Yeah, it's good to have this little feedback as well, so we can improve user experience. So you can upload screens, details.

Daniyal Sultan
You can click so you can skip or you can

Mike Volkin
continue.

Mike Volkin
Like it.

Daniyal Sultan
Once you save your profile, then you come to this screen where we. We have these.

Daniyal Sultan
Onboarding like a tutorial.

Daniyal Sultan
We can finish this or skip this.

Daniyal Sultan
So this is our, like, main dashboard.

Daniyal Sultan
Where we have the option to, like, join a meeting through link.

Daniyal Sultan
Any recent activities or data.

Daniyal Sultan
You can create a workspace, create a folder.

Daniyal Sultan
Then we have, like, a workspace tab.

Daniyal Sultan
This is like a workspace, basically built on default.

Daniyal Sultan
If you go into this.

Daniyal Sultan
Then you can actually. You have, like, a default folder.

Daniyal Sultan
You can also add more folders or create more. Then you have meetings.

Daniyal Sultan
This is Tab. If you don't want to go into workspaces, then folders and you want to just quickly, you know, have a look at your past meetings.

Daniyal Sultan
We have added, like, a tab for all meetings.

Daniyal Sultan
I like it. Every meeting. Data will be available here. You can search. I have like an account ready with some data.

Daniyal Sultan
So I will be switching onto that as well so we can look into how the transcriptions are coming. Folders are being populating with data and stuff. Then we have like a tab for unassigned meetings.

Daniyal Sultan
So basically, we added this t.

Daniyal Sultan
To keep in view the use case of if, you know, Ellie joins a meeting.

Daniyal Sultan
I have, like, a meeting with you.

Daniyal Sultan
And there could be, like, other people in the meeting as well.

Daniyal Sultan
So just. And, you know, if we are a team, let's assume we are a company.

Daniyal Sultan
And we are doing like a meeting for invite Ali. Then we also do like a meeting for our. We are working on another application.

Daniyal Sultan
Like, a travel app. So we have, like, an internal meeting for that.

Daniyal Sultan
Too. So you know, it. It could become difficult for Alink to just based on the emails that data basically based on participants to decide where this meeting data is going to go into which folder.

Daniyal Sultan
So because, you know, same people can have, you know, same participants can talk about different projects.

Daniyal Sultan
But the purpose of keeping Memory Insight folders is to keep it very organized based on the user preference. So it could be related to projects or it could be related to departments. So, you know, between a team, you know, participants can be similar for different departments as well.

Daniyal Sultan
So to do this we have added like tab for unassigned meetings. We can definitely work on the messaging over here to help us help our users and started pattern. But how it works is whenever like you whenever like a meeting completes, the meeting comes over here. A user has the ability to pre assign a meeting.

Daniyal Sultan
So let's

Mike Volkin
assume

Daniyal Sultan
you schedule a meeting with me in your calendar. You can come to Ali.

Daniyal Sultan
And assign that meeting to a folder so automatically that data will flow.

Daniyal Sultan
If you don't assign. Once the meeting is completed, you can come over here and sign that to a folder. Let me just log into an account which has that some data.

Daniyal Sultan
So I can show you how it works.

Daniyal Sultan
So basically, you can use like, these are the meetings which are unassigned.

Daniyal Sultan
So for the meeting we are having right now, when you enter a link I pre assigned it so it will automatically go into the folder I have in this workspace relevant to it. So these are like unassigned. You have like the details, meeting title, the workspace.

Daniyal Sultan
The platform and some details about the meeting itself. The summary action item.

Daniyal Sultan
And the meeting transcription as well. From here you can select any folder, any existing one, or you can create a new folder, and once you click on it.

Daniyal Sultan
It will be assigned to that.

Daniyal Sultan
Folder.

Daniyal Sultan
So what happens when you do this is basically, if I go to that.

Daniyal Sultan
Specific workspace.

Daniyal Sultan
And to this folder.

Daniyal Sultan
So this is like, because we have live transcription, ongoing.

Daniyal Sultan
So I presigned this call.

Daniyal Sultan
Like the call we are having right now. So the transcription is going and they are in real time.

Daniyal Sultan
These are some pass meetings. And the. And the one I just assigned to this folder.

Daniyal Sultan
From here you can see if you select a meeting.

Daniyal Sultan
This is I can call ongoing. So we don't have any summary or action items over here.

Daniyal Sultan
For this one.

Daniyal Sultan
For previous ones. This one was related to contextual matches. So you can see you have, like a meeting impact score.

Daniyal Sultan
Which defines decision making, action, clarity,

Daniyal Sultan
Stakeholder engagement, productivity. Then you have, like, a summary.

Daniyal Sultan
And some action items here you have like all the transcript.

Daniyal Sultan
And you can also use these buttons.

Daniyal Sultan
To export.

Daniyal Sultan
To slack notion or HubSpot.

Daniyal Sultan
I just exported it to Slack. Let me share my screen.

Daniyal Sultan
Slack as well.

Daniyal Sultan
So I can show you.

Daniyal Sultan
So I have my slack integrated. I will show you in a moment how you can integrate user then actually integrate this slack with Ali as well.

Daniyal Sultan
The ALI testing four contextual nudges. You have like the summary and that action items.

Daniyal Sultan
Exported to Slab. Similar is the flow for HubSpot and Notion.

Daniyal Sultan
So you can create different folders and then assign meetings to it.

Daniyal Sultan
Then we have, like, this live meeting assessment.

Daniyal Sultan
Where you can actually for any ongoing meetings, like we are having like a meeting right now. It has memory for the previous meetings and also for the live. You can ask any questions.

Daniyal Sultan
Related to, like the present meeting.

Daniyal Sultan
Also, based on any previous meetings.

Daniyal Sultan
I will demo that to you in a moment as well. Let me just first show you some of the transcript and summaries and action items from some of our like, previous meetings and then we can ask those questions in the live meeting Assistant tab as well.

Daniyal Sultan
So we have over here.

Daniyal Sultan
For, like, past meeting, for contextual matches.

Daniyal Sultan
The summary is it was led by Daniel Sultan. The action items include Daniel and Salman Coordinate to coordinate with the developer team to carry out thorough testing of contextual nudges.

Daniyal Sultan
With a focus on adding data sets or for different use cases.

Daniyal Sultan
Such as sales, our developer teams to validate its performance.

Daniyal Sultan
Salman to work with the developer team to add data sets for VLC various use cases to the contextual managers features, with the goal of minimizing hallucinations and increasing relevant answers and to validate features eligibility.

Daniyal Sultan
To carry context over and also to focus on the topics discussed in the meeting, including the creation of large data sets.

Daniyal Sultan
For different use cases.

Daniyal Sultan
So.

Daniyal Sultan
Let me.

Mike Volkin
Also be not interested in knowing what the meeting impact score is. Maybe a little eye icon.

Mike Volkin
Next to the title of the meeting.

Daniyal Sultan
Impact

Mike Volkin
section. Just to find what it is. Because I don't know what it is. It's a score of some kind.

Mike Volkin
But

Daniyal Sultan
sounds cool.

Daniyal Sultan
Yes, you can add some messaging over there.

Daniyal Sultan
So this is like it provides a contextual measures. Sorry, contextual edges in ALI provide contacts based on previous meetings, helping users get better inside reading calls.

Daniyal Sultan
They are available online Meeting assistant tag. They aim to minimize hallucination and increase relevant answers. So based on the context it has for like my previous meeting data, it is actually adding. Basically it is carrying the context.

Daniyal Sultan
That the things we discussed in the meeting, that what context images are and how they should perform.

Daniyal Sultan
If I ask what are.

Daniyal Sultan
The action.

Daniyal Sultan
Icon.

Daniyal Sultan
So it gave me, like daniel and salman to test and evaluate the feature salman to add data sets for various use cases.

Daniyal Sultan
And Daniel to focus on creating large data sets.

Daniyal Sultan
So what we have aimed to do in this tab is to keep answers very brief.

Daniyal Sultan
Not to, you know, because this is. This is something like if we are having a meeting, so that it should be to the point, so it's assistive to the user and it does not, you know, take a lot of my attention or I have to actually read a lot.

Daniyal Sultan
Based on that? It can. Let me just test, because it's getting the data from our transcript right now.

Daniyal Sultan
I. And this is a feature that is, like, in testing, it's not completely ready.

Daniyal Sultan
So there can be some errors or, like, we should not have, like, high expectations. This is something we are just working on.

Daniyal Sultan
Basically, I just asked.

Daniyal Sultan
Ali, about the demo call with you.

Daniyal Sultan
And based on, like, the data it's receiving in real time, it gave me, like, scheduled for today discussion.

Daniyal Sultan
Is or like, invite any features.

Daniyal Sultan
Review of meeting workflow and question and answer session. So can you tell

Mike Volkin
me.

Mike Volkin
Oh, sorry. Can you do me? I have a quick thought. I just asked you to do something like a minute or two minutes ago. Can you type into that search bar?

Mike Volkin
What? What did Mike ask me to do in regards to the strategic impact score? Let's see if it brings up.

Daniyal Sultan
Yes.

Mike Volkin
Mike asked to add sentiment analysis, topic modeling. I'm not sure I did that. I

Daniyal Sultan
just

Mike Volkin
asked to define a little eye icon and define the strategic impact scores. Yeah.

Daniyal Sultan
So it's like evolving something we are working on.

Daniyal Sultan
So all the feedback and data we get, it's going to get better.

Daniyal Sultan
So, you know, it will obviously, you know, be better based on the feedback and testing. Okay?

Daniyal Sultan
Then we have like a tab for contextual. For this to be active, we should we having like a meeting with like the same participant. So if you and me are having this meeting today,

Daniyal Sultan
And then we schedule another call, like tomorrow or like CMD or like after a week.

Daniyal Sultan
So with the same participant.

Daniyal Sultan
Ali would show some contextual nudges in this tab.

Daniyal Sultan
Because, you know, if we too, are having a meeting, and it should show context only relevant to the same participant.

Mike Volkin
Okay?

Mike Volkin
Because the title of the other tab is

Daniyal Sultan
Live Meeting Assistant.

Mike Volkin
But now in this contextual, nudges, it says this part can only be during live meetings. So it's a little confusing. It's like, why isn't that in a live meeting? Assistant tab.

Mike Volkin
We might need to rephrase that a little bit because

Daniyal Sultan
it's. It was. You can work on the messaging.

Daniyal Sultan
We just spent time on the functionality, on the user experience. SALMAN has to. You know, we can work with SALMAN to improve the user experience or the messaging.

Daniyal Sultan
The core focus was to like, just do like an early demo for these add on features.

Daniyal Sultan
So I also had this.

Daniyal Sultan
You can say point of view that the messaging can be improved for this live meeting. Assistant.

Daniyal Sultan
Also because you can access this tab.

Daniyal Sultan
When you are not even having a live meeting.

Daniyal Sultan
To actually have a conversation.

Daniyal Sultan
About past meetings and stuff. So if I'm not having, like, a live meeting, I might still need to have, like, a conversation with Ali to, you know, get to know about my past meetings or decisions I made.

Daniyal Sultan
So that feature is available if I refresh this page.

Daniyal Sultan
You can have this conversation even if you are not having an active meeting.

Daniyal Sultan
But we can, you know, work better with the messaging and how to position it.

Daniyal Sultan
So it's more as you said.

Daniyal Sultan
Better in terms of user experience.

Daniyal Sultan
So I have, like,

Daniyal Sultan
I did some testing. I can show you.

Daniyal Sultan
A screenshot that I took.

Daniyal Sultan
For these contextual address. How the RXB coming along? Let me share my screen.

Daniyal Sultan
So if. Can you see this thing right now?

Mike Volkin
I see it, says Ellie, meeting assistant, and

Daniyal Sultan
has

Mike Volkin
contextual nudges.

Daniyal Sultan
These features are like these, you know, things we are talking on. We would very much welcome your feedback.

Daniyal Sultan
And direction as well, because this is like a work in progress.

Daniyal Sultan
And how we present these or how we can even work on them to improve them.

Daniyal Sultan
That would be really helpful and, you know, fine tuning or even improving these features. So if you have, like, an ongoing meeting with the same participant,

Daniyal Sultan
Then based on the context you had from the previous meeting, there would be some context in nudges, and there are some tags identified in the system as well. Like this contextual nudge is general. We have like six to seven different tags. I will share them with you over email.

Daniyal Sultan
So the idea we gave different colors.

Daniyal Sultan
For different tags. So when you are having a meeting. So if the if you are familiar with tags.

Daniyal Sultan
You know, visually, it will grab the attention of the user. To know like this nudge is more important.

Daniyal Sultan
So, you know, just to play with the user experience itself.

Mike Volkin
I like that. Why does it have to be the same user? Because the way I've been pitching Ellie to other people is like, let's say there's a finance. Let's say the finance department is in on a meeting a month ago with us and they talk about our budget, and then you and. I are talking about a budget and some things, and I would like Ellie to be able to say, wait a second. Finance says you don't have the money for, for this because you're talking about something that's 200,000 and your budget is only 180,000.

Mike Volkin
You know, it's supposed to

Daniyal Sultan
be

Mike Volkin
cross functional between departments.

Mike Volkin
Does

Daniyal Sultan
it have to be

Mike Volkin
the

Daniyal Sultan
same

Mike Volkin
the same attendees for the contextual nudges to happen?

Daniyal Sultan
Is basically.

Daniyal Sultan
For? Just give me a moment.

Daniyal Sultan
Because.

Daniyal Sultan
Sorry about that.

Daniyal Sultan
So idea behind it is basically, if we don't add, you know, this restriction we can work on. I get your idea.

Daniyal Sultan
And we can work on like this use case.

Daniyal Sultan
As well to refine it further. But the idea behind current implementation is if we don't define like participants.

Daniyal Sultan
What will happen is basically, we don't want our context to have, like, hallucinations.

Daniyal Sultan
Just based on if you. Let's assume if we are having, like, a meeting for, like, demo right now.

Daniyal Sultan
And we have, like, a bunch of other meetings.

Daniyal Sultan
In this week.

Daniyal Sultan
I had, like, a bunch of other calls with, like, other departments or other projects.

Daniyal Sultan
If after a week.

Daniyal Sultan
If we don't define it based on like.

Daniyal Sultan
Participant, so it would become difficult for any to actually it can happen.

Daniyal Sultan
Using AI.

Daniyal Sultan
To, you know, but because once the meeting has started,

Daniyal Sultan
It would take some time for Ali to recognize what this meeting is about if we are just using memory

Mike Volkin
and

Daniyal Sultan
context. So see what's happening and to which data set or, like, which part of memory it's relevant.

Daniyal Sultan
And what we are talking about and what context would be relevant, it. It brings that over.

Daniyal Sultan
So for now, what we did to make it, like, highly accurate or relevant.

Daniyal Sultan
Is once. I am having a meeting with you.

Daniyal Sultan
Because the participants are same, it becomes it easier.

Daniyal Sultan
For Ali to go into those data sets and then. But I will spend some more time on it.

Daniyal Sultan
To actually, like, look into it. It more like how we can not make it participant specific or even make it participant specific like we have right now.

Daniyal Sultan
But also enhance its ability.

Daniyal Sultan
If you had a call with, like, a client.

Daniyal Sultan
And then you have, like, a meeting

Mike Volkin
with me.

Daniyal Sultan
But you want that context to be carried over into the meeting with me as well.

Daniyal Sultan
So that could happen as well. I will spend some more time and see what

Mike Volkin
we can do.

Mike Volkin
Okay, thank you.

Daniyal Sultan
So the cross meeting memory is functional.

Daniyal Sultan
So Ali does have ability to, you know, have context and memory over, like,

Mike Volkin
department

Daniyal Sultan
folders and work.

Daniyal Sultan
So that is why this like we are able to ask anything over here about any workspace, any folder, any meeting.

Daniyal Sultan
And it comes up with those responses.

Mike Volkin
How. How far back

Daniyal Sultan
does the memory go?

Daniyal Sultan
So the memory limit.

Daniyal Sultan
You know what we have?

Daniyal Sultan
In our system is like 90 days.

Daniyal Sultan
And, you know, users can also, as we decided they can like, pin folders right now because we are in like transcription. Largely, the data that is being stored are like transcription. So it's not very data heavy.

Daniyal Sultan
it won't increase our cost. But once we start to add those videos or like images, those features will definitely take space. But right now we have retention till 90 days.

Daniyal Sultan
With ability for users to, you know, if they want to retain folders, they can select and retain those folders. And those folders memories would be retained.

Daniyal Sultan
Would it

Mike Volkin
help if I started using this for my meetings?

Mike Volkin
Is it too early for that, or just. Just

Daniyal Sultan
to help

Mike Volkin
get some testing in there?

Daniyal Sultan
I will share like. Basically, we need to move it to production.

Daniyal Sultan
After this demo call, I will, you know, any feedback that we have, you know, we will work on it.

Daniyal Sultan
And for the features that are ready, we will ship those to production and I will share like a link with you, like a production URL.

Daniyal Sultan
Which you can start using for your meetings as well.

Daniyal Sultan
I can. And then you can, you know, add as much data as you want.

Daniyal Sultan
Because then we have to. Also, as I mentioned, I don't want to basically, you know, in the production database.

Daniyal Sultan
Are, you know, testing data and stuff, so we plan to keep it clean.

Daniyal Sultan
So, you know, after this call, we will address any feedback and then move to production.

Daniyal Sultan
And then share a user with you, which you can also use. And also we can onboard any, you know, users.

Daniyal Sultan
Like some initial testing users that we want.

Daniyal Sultan
To start adding some data in it and based on feedback we can improve and polish before launch.

Mike Volkin
Do you have everything you need from him?

Daniyal Sultan
Yeah, so far.

Daniyal Sultan
Everything that you mentioned, we have addressed it.

Daniyal Sultan
The only thing that he wants is to test like the production environment for that. After our call, as I mentioned, we will start moving things to production so he can do like a final round of testing.

Daniyal Sultan
We had, like, a call for the backend developer with Jesse, and even together through all the flows and stuff and made sure the practices we have are, like,

Mike Volkin
compliant. Okay, great.

Mike Volkin
Thank you very much.

Mike Volkin
Can we also get the elephant icon for the le that's joined here? It just has E. It'd just be good to have the icon or the logo on

Daniyal Sultan
there, rather than just look into it. And because this is like being managed from recall. So I will look into it and see if

Mike Volkin
that's possible.

Mike Volkin
Okay. A couple things I want to talk to you about, if you don't mind. Unless you have other things that you want to show me.

Daniyal Sultan
Yeah, just like a bunch of things that are left. I'll be quick and then, you know, I will be welcome in your feedback. We have like a tab for notifications, ADC audio notifications.

Daniyal Sultan
Then you have preferences, profile and integrations. You have this page which you can use to correct a Google Calendar, Microsoft Slack HubSpot notion.

Daniyal Sultan
You have, like, a page for subscriptions, right? Is attached to it.

Daniyal Sultan
This is for. And this is like, just like we have added placeholders.

Daniyal Sultan
Because we had to integrate

Mike Volkin
stripe.

Daniyal Sultan
Then we have, like, a tab for testing.

Daniyal Sultan
And that is all I think we have.

Daniyal Sultan
One thing. Last thing I miss. This is something.

Daniyal Sultan
I shared like a gnome with you.

Daniyal Sultan
But this is like our AI system. I think for this you also shared some documents for training and stuff. So we have done some work on this.

Daniyal Sultan
Too. You can add. You can ask anything about the features.

Daniyal Sultan
What?

Daniyal Sultan
All that fuel. Message.

Mike Volkin
Does it have safeguards in there? I mean, what if, when it says, how can I help you today? What? It says, help me build a weapon or something silly. You know, people are going to test us.

Daniyal Sultan
This stuff like that.

Daniyal Sultan
Some gardens. That is possible.

Daniyal Sultan
So this is all that I have.

Daniyal Sultan
For today's demo and I would actually like to know your feedback, how you feel about the system. Definitely there will be some improvement. Some things we can work on to make it, you know, better in terms of user experience. Also build

Mike Volkin
functionality.

Mike Volkin
Yeah, I mean, everything looks good so far. I definitely want to test it and have some meetings where I can recall facts and see how accurate is. But from a user standpoint, it looks.

Daniyal Sultan
Pretty good.

Mike Volkin
How much? Like, what's the next step? Are you guys going to do some more testing on each feature?

Mike Volkin
And

Daniyal Sultan
what's the

Mike Volkin
timeline

Daniyal Sultan
on

Mike Volkin
that?

Daniyal Sultan
So the next thing we are going to do, we are just going to address some feedback and add some. I will be doing some more testing as well.

Daniyal Sultan
And from now on, we will be having, like, a weekly meeting.

Daniyal Sultan
Because, you know, these features do have, like, a foundation right now.

Daniyal Sultan
So it's good to have, like, a call every week and, you know, for every week we have some, you know, we work on user experience and things related to the product, and then we can talk about enhancements or any other if we want. We can also, you know, talk about different features.

Daniyal Sultan
Like their functionality and stuff.

Daniyal Sultan
So, about the timeline, I would say in, like, two weeks.

Daniyal Sultan
We will have like the production URL ready.

Daniyal Sultan
And by then we will have that tested by Jesse as well.

Daniyal Sultan
For compliance.

Daniyal Sultan
We can address any feedback he has.

Daniyal Sultan
In this timeline too. So we the production URL has everything it needs related to compliance and also related to the product like feature

Mike Volkin
set as well.

Mike Volkin
Sounds good.

Daniyal Sultan
Oh, go ahead. Yeah, please.

Mike Volkin
Oh, I was just going to bring up a couple closing points, but if you have something else regarding this, let's go ahead and square that off.

Daniyal Sultan
It's fine.

Daniyal Sultan
Yeah.

Daniyal Sultan
So for phase one, we had these features to be taken care of.

Daniyal Sultan
Like workspace creation.

Daniyal Sultan
Folders, basic integrations.

Daniyal Sultan
Mating transcription.

Daniyal Sultan
Basic context prep Full last meeting notes from folder.

Daniyal Sultan
Post meeting summary.

Daniyal Sultan
Memory per folder export push admin basics.

Daniyal Sultan
So this admin, this is like the admin dashboard where you can see all the data we have inside. Ali. This is like a bit technical because it has been kept that way so we can add more. You know, we can even add stuff related to how the app is performing, how the backend is going. So those things are added in this tool and for you as well. We will add some tutorial so it's easier for you to navigate.

Daniyal Sultan
Then let me. I need to show you two more screenshots.

Daniyal Sultan
Based on the participants. What happens if, like, I have a meeting with you next week?

Daniyal Sultan
So before our meeting, we are also sending an email.

Daniyal Sultan
With, like, contacts from our, like, previous meeting.

Daniyal Sultan
So it also, you know, reminds the user in a way about the summary and action items and help them get, like, a

Mike Volkin
better

Daniyal Sultan
understanding.

Daniyal Sultan
About

Mike Volkin
context.

Mike Volkin
Yeah. Yeah, that'll be helpful.

Daniyal Sultan
For user to also to remind them to assign meetings to relevant folders.

Daniyal Sultan
What we have done is if for a meeting I do not assign any folder.

Daniyal Sultan
You're also sending, like, an email.

Daniyal Sultan
The meeting ends and like after 10 minutes, if the meeting data is not assigned to any folder.

Daniyal Sultan
We will send. We are sending out this email and this email, you can see you're available folders.

Daniyal Sultan
You can just click on it and it assigns that meeting data.

Daniyal Sultan
To that specific

Mike Volkin
folder.

Mike Volkin
Yeah, I like that.

Mike Volkin
Great. Good thinking on that. Yeah.

Mike Volkin
Yeah. I like the workflow you guys have put together. You're thinking about things from all the angles. That's nice. Okay, a couple things. Let me bring up.

Mike Volkin
My thing.

Mike Volkin
So if last week there has been two new competitors alone

Daniyal Sultan
just last

Mike Volkin
week, companies that take AI meeting notes and do contextual memory, this one company does recall as well. But they do like this whole book. Like, you have to read everything. The recall we're going to do, hopefully, is just one or two sentences like, hey, Wait a second. There's a discrepancy here. So they're coming in hot and heavy.

Mike Volkin
With that said, I hired a specialist to do like this business analyst.

Mike Volkin
On business models. There may be maybe a strategic shift coming soon. Not a pivot of a business model, but just a shift with how we approach things.

Mike Volkin
So I've got a vacation coming up. From the 5th through the 13th, I'll be in Costa Rica.

Mike Volkin
There'll be some long flights. It's a working vacation. I'm going to be dedicating that week to go through her report. She did a very thorough job.

Daniyal Sultan
I just haven't reviewed

Mike Volkin
I'm going to hold off on trying to raise funds.

Mike Volkin
So right now, everything that I'm doing,

Mike Volkin
So please do not do any other work before giving me an estimate and a potential invoice. So I just don't want to be surprised by an invoice and

Daniyal Sultan
be like,

Mike Volkin
wait a second, I don't have the money for that. That's the last thing I want is for you not to. Get paid. So, moving forward, if there's anything over and above what I've already paid you,

Daniyal Sultan
please,

Mike Volkin
let's line item that out and

Daniyal Sultan
prioritize

Mike Volkin
it, because we're still working on limited funds. Of course.

Daniyal Sultan
Okay.

Mike Volkin
Makes sense.

Daniyal Sultan
Yeah. For that right now, we only have, you know, these.

Daniyal Sultan
Features.

Daniyal Sultan
These are the things that I have demoed to you.

Daniyal Sultan
And these are the add ons like silent qa, the AI assistant, contextual nudges, impact score and cross meeting summary.

Daniyal Sultan
Budget for these, like we already discussed, but we didn't make, like, a decision on it.

Daniyal Sultan
So. But, you know, we decided to give you, like, an Adri demo because, you know, we were very much concerned about the timelines and stuff.

Daniyal Sultan
So we have, as I showed you.

Daniyal Sultan
Made progress on it and, like, it's largely polishing and stuff.

Daniyal Sultan
So, you know, the idea is to. As you mentioned, for an AI Company, every week is like any year.

Daniyal Sultan
So, you know, we. These features are looking good to be launched very soon.

Daniyal Sultan
As

Mike Volkin
well.

Mike Volkin
Okay, yeah, let's. Let's. So the add on section is what's going to require an extra invoice, is what you're saying.

Daniyal Sultan
So that is something pending on

Daniyal Sultan
Okay. Makes sense. Yeah. I will just, you know, tag you in that thread.

Daniyal Sultan
No, this is all that I have.

Daniyal Sultan
And we are working on refining these features.

Daniyal Sultan
And as you mentioned about your vacations next week, so if your calendar, you know, we can stay in touch over emails.

Mike Volkin
Okay, Sounds good. I appreciate the update. Thanks. Everything looks good so far.

Daniyal Sultan
Thank you so much.

Mike Volkin
Take care. Bye.

Daniyal Sultan
All right, take care. (this is the transcription)"""


def main():
    parser = argparse.ArgumentParser(description='Test summary generator with transcript')
    parser.add_argument('--file', type=str, help='Path to transcript file')
    parser.add_argument('--text', type=str, help='Transcript text directly')
    parser.add_argument('--sample', action='store_true', help='Use sample transcript for testing')
    
    args = parser.parse_args()
    
    transcript_text = None
    
    # Get transcript from different sources
    if args.file:
        print(f"📂 Reading transcript from file: {args.file}")
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                transcript_text = f.read()
        except Exception as e:
            print(f"❌ ERROR: Failed to read file: {e}")
            sys.exit(1)
    elif args.text:
        transcript_text = args.text
    elif args.sample:
        # Sample transcript for quick testing
        transcript_text = """Meeting Transcript - Sample Test Meeting

John: Good morning everyone, thanks for joining. Let's start with the project status update.

Sarah: Hi John, I've completed the frontend implementation for the user dashboard. It's ready for review.

Mike: Great! I've been working on the backend API. We need to integrate the authentication system.

John: Perfect. Sarah, can you send the PR by end of day? Mike, let's schedule a meeting tomorrow to discuss the API integration.

Sarah: Yes, I'll have it ready by 5 PM today.

Mike: Sounds good. I'll prepare the API documentation for tomorrow's meeting.

John: Excellent. One more thing - we need to update the database schema. Mike, can you handle that?

Mike: Sure, I'll create a migration script and test it by Friday.

Sarah: I can help test the migration once it's ready.

John: Perfect. Let's wrap up. Action items: Sarah sends PR by 5 PM today, Mike prepares API docs for tomorrow, and Mike creates database migration by Friday. Meeting adjourned."""
    else:
        # Use TRANSCRIPT variable from the file (OPTION 1)
        transcript_text = TRANSCRIPT.strip()
        
        # Check if it's still the placeholder
        if not transcript_text or len(transcript_text) < 10 or "Paste your meeting transcription" in transcript_text:
            print("=" * 80)
            print("⚠️  WARNING: No transcription provided!")
            print("=" * 80)
            print("\nTo use this test script:")
            print("  1. Edit this file and paste your transcription in the TRANSCRIPT variable (lines 30-34)")
            print("  2. Or run: python test_summary_generator.py --file path/to/transcript.txt")
            print("  3. Or run: python test_summary_generator.py --text \"Your transcript here...\"")
            print("  4. Or run: python test_summary_generator.py --sample (for quick test)")
            print("\nExample:")
            print("  python test_summary_generator.py --file ../test_meeting_script.txt")
            print("  python test_summary_generator.py --text \"Meeting transcript here...\"")
            sys.exit(1)
    
    # Validate transcript
    if not transcript_text or len(transcript_text.strip()) < 10:
        print("❌ ERROR: Transcript is too short or empty!")
        print("   Minimum length: 10 characters")
        sys.exit(1)
    
    # Run the test
    test_summary_generation(transcript_text)


if __name__ == '__main__':
    main()


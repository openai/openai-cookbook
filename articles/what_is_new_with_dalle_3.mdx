# What’s new with DALL·E-3?

DALL·E-3 is the latest version of our DALL-E text-to-image generation models. As the current state of the art in text-to-image generation, DALL·E is capable of generating high-quality images across a wide variety of domains. If you're interested in more technical details of how DALL·E-3 was built, you can read more about in our [research paper](https://cdn.openai.com/papers/dall-e-3.pdf). I'll be going over some of the new features and capabilities of DALL·E-3 in this article, as well as some examples of what new products you can build with the API.

As a reminder, the Image generation API hasn't changed and maintains the same endpoints and formatting as with DALL·E-2. If you're looking for a guide on how to use the Image API, see [the Cookbook article](https://cookbook.openai.com/examples/dalle/image_generations_edits_and_variations_with_dall-e) on the subject.

The only API endpoint available for use with DALL·E-3 right now is **Generations** (/v1/images/generations). We don’t support variations or inpainting yet, though the Edits and Variations endpoints are available for use with DALL·E-2.

## Generations

The generation API endpoint creates an image based on a text prompt. There’s a couple new parameters that we've added to enhance what you can create with our models. Here’s a quick overview of the options:

### New parameters:

- **model** (‘dall-e-2’ or ‘dall-e-3’): This is the model you’re generating with. Be careful to set it to ‘dall-e-3’ as it defaults to ‘dall-e-2’ if empty.
- **style** (‘natural’ or ‘vivid’): The style of the generated images. Must be one of vivid or natural. Vivid causes the model to lean towards generating hyper-real and dramatic images. Natural causes the model to produce more natural, less hyper-real looking images. Defaults to ‘vivid’.
- **quality** (‘standard’ or ‘hd’): The quality of the image that will be generated. ‘hd’ creates images with finer details and greater consistency across the image. Defaults to ‘standard’.

### Other parameters:

- **prompt** (str): A text description of the desired image(s). The maximum length is 1000 characters. Required field.
- **n** (int): The number of images to generate. Must be between 1 and 10. Defaults to 1. For dall-e-3, only n=1 is supported.
- **size** (...): The size of the generated images. Must be one of 256x256, 512x512, or 1024x1024 for DALL·E-2 models. Must be one of 1024x1024, 1792x1024, or 1024x1792 for DALL·E-3 models.
- **response_format** ('url' or 'b64_json'): The format in which the generated images are returned. Must be one of "url" or "b64_json". Defaults to "url".
- **user** (str): A unique identifier representing your end-user, which will help OpenAI to monitor and detect abuse. Learn more.

## New Features

Our launch of DALL·E-3 comes with lots of new features and capabilities to help you generate the images you want. Here’s a quick overview of what’s new:

### Prompt Rewriting

A new feature in the latest DALL·E-3 API is prompt rewriting, where we use GPT-4 to optimize all of your prompts before they’re passed to DALL-E. In our research, we’ve seen that using very detailed prompts give significantly better results. You can read more about our captioning, prompting, and safety mitigations in the [DALL·E-3 research paper](https://cdn.openai.com/papers/dall-e-3.pdf).

_Keep in mind that this feature isn’t able to be disabled at the moment, though you can achieve a high level of fidelity by simply giving instructions to the relabeler in your prompt, as I'll show below with examples._

![Prompt Rewriting](/images/dalle_3/dalle_3_improved_prompts.png)

### Standard vs HD Quality

DALL·E-3 introduces a new 'quality' parameter that allows you to adjust the level of detail and organization in all of your generations. The 'standard' quality generations are the DALL·E-3 you're familiar with, with 'hd' generations bringing a new level of attention to detail and adherence to your prompt. Keep in mind that setting your generation quality to ‘hd’ does increase the cost per image, as well as often increasing the time it takes to generate by ~10 seconds or so.

For example, here we have two different icons in 'hd' and 'standard' quality. Often the choice between either quality is up to taste, but 'hd' often wins when the task requires more ability to capture details and textures or better composition of a scene.

![Icons](/images/dalle_3/icons.jpg)

Here's another example, this time with a prompt of 'An infinite, uniform grid of tessellated cubes.', which DALL·E conveniently rewrites as _"An infinite, uniform grid of tessellated cubes painted carefully in an isometric perspective. The cubes are meticulously arranged in such a way that they seem to stretch endlessly into the distance. Each cube is identical to the next, with light reflecting consistently across all surfaces, underscoring their uniformity. This is a digitally rendered image."_:

![Cubes](/images/dalle_3/cubes.jpg)

### New Sizes

DALL·E-3 accepts three different image sizes: 1024px by 1024px, 1792px by 1024px, and 1024px by 1792px. Beyond giving more flexibility in terms of aspect ratio, these sizes can have significant effects on the style and context of your generated image. For example, vertical images might work better when you’re looking for an image that looks like it was taken by a cellphone camera, or horizontal images may work better for landscape paintings or digital designs.

To demonstrate this difference, here’s multiple variations on the same input prompt with a different aspect ratio. In this case, my prompt was: “Professional photoshoot of a Chemex brewer in the process of brewing coffee.” (For reference, this is a photo of [a real Chemex brewer](https://m.media-amazon.com/images/I/61lrld81vxL.jpg)).

Here is the generation in square form (in both HD and standard qualities):

![square_coffee](/images/dalle_3/square_coffee.jpg)

You can see how these images are framed closely to the item and seem to be taken in a more closed space with various surrounding items nearby.

Here are the results on the same prompts with a wider aspect ratio:

![wide_coffee](/images/dalle_3/wide_coffee.jpg)

Compared to the previous generations, these come in the form of close-ups. The background is blurred, with greater focus on the item itself, more like professionally organized photoshoots rather than quick snaps.

Lastly, we have the vertical aspect ratio:

![tall_coffee](/images/dalle_3/tall_coffee.jpg)

These feel more akin to cellphone images, with a more candid appearance. There’s more action involved: the slowly dripping coffee or the active pour from the pot.

### New Styles

DALL·E-3 introduces two new styles: natural and vivid. The natural style is more similar to the DALL·E-2 style in its 'blander' realism, while the vivid style is a new style that leans towards generating hyper-real and cinematic images. For reference, all DALL·E generations in ChatGPT are generated in the 'vivid' style.

The natural style is specifically useful in cases where DALL·E-3 over-exaggerates or confuses a subject that's supposed to be more simple, subdued, or realistic. I've often used it for logo generation, stock photos, or other cases where I'm trying to match a real-world object.

Here's an example of the same prompt as above in the vivid style. The vivid is far more cinematic (and looks great), but might pop too much if you're not looking for that.

![vivid_coffee](/images/dalle_3/vivid_coffee.jpg)

There's many cases in which I prefer the natural style, such as this example of a painting in the style of Thomas Cole's 'Desolation':

![thomas_cole](/images/dalle_3/thomas_cole.jpg)

## Examples and Prompts

To help you get started building with DALL·E-3, I've come up with a few examples of products you could build with the API, as well as collected some styles and capabilities that seem to be unique to DALL·E-3 at the moment. I've also listed some subjects that I'm struggling to prompt DALL·E-3 to generate in case you want to try your hand at it.

### Icon Generation

Have you ever struggled to find the perfect icon for your website or app? It would be awesome to see a custom icon generator app that lets you pick the style, size, and subject of your icon, and then generates a custom SVG from the DALL·E generation. Here's some examples of helpful website icons I generated with DALL·E-3:

![icon_set](/images/dalle_3/icon_set.jpg)

In this case, I used Potrace to convert the images to SVGs, which you can download [here](https://potrace.sourceforge.net/). This is what I used to convert the images:

```bash
potrace -s cat.jpg -o cat.svg
```

You might need to boost the brightness and contrast of the image before converting it to an SVG. I used the following command to do so:

```bash
convert cat.jpg -brightness-contrast 50x50 cat.jpg
```

### Logo Generation

DALL·E-3 is great at jumpstarting the logo creation process for your company or product. By prompting DALL·E to create 'Vector logo design of a Greek statue, minimalistic, with a white background' I achieved the following:

![logo_greece](/images/dalle_3/logo_greece.jpg)

Here's another logo I created, this time for an Arabian coffee shop:

![logo_arabia](/images/dalle_3/logo_arabia.jpg)

In the case of iterating on an existing logo, I took OpenAI's logo, asked GPT-4V to describe it, and then asked DALL·E to generate variations on the logo:

![iteration](/images/dalle_3/iteration.jpg)

### Custom Tattoos

DALL·E-3 is great at generating line art, which might be useful for generating custom tattoos. Here's some line art I generated with DALL·E-3:

![tattoos](/images/dalle_3/tattoos.jpg)

### Die-Cut Stickers & T-Shirts

What if you could generate custom die-cut stickers and t-shirts with DALL·E-3, integrating with a print-on-demand service like Printful or Stickermule? You could have a custom sticker or t-shirt in minutes, with no design experience required. Here's some examples of stickers I generated with DALL·E-3:

![stickers](/images/dalle_3/stickers.jpg)

### Minecraft Skins

With some difficulty, I managed to prompt DALL·E-3 to generate Minecraft skins. I'm sure with some clever prompting you could get DALL·E-3 to reliably generate incredible Minecraft skins. It might be hard to use the words 'Minecraft' since DALL·E might think you are trying to generate content from the game itself, instead, you can communicate the idea differently: "Flat player skin texture of a ninja skin, compatible with Minecraftskins.com or Planet Minecraft."

Here's what I managed to create. They might need some work, but I think they're a good start:

![minecraft](/images/dalle_3/minecraft.jpg)

### And much more...

Here's some ideas I've had that I haven't had time to try yet:

- Custom emojis or Twitch emotes?
- Vector illustrations?
- Personalized Bitmoji-style avatars?
- Album art?
- Custom greeting cards?
- Poster/flyer 'pair-programming' with DALL·E?

## Showcase

We're really just starting to figure out what DALL·E-3 is capable of. Here's some of the best styles, generations, and prompts I've seen so far. I've been unable to locate the original authors of some of these images, so if you know who created them, please let me know!

![collage](/images/dalle_3/collage.jpg)

Sources:

[@scharan79 on Reddit](https://www.reddit.com/r/dalle2/comments/170ce1r/dalle_3_is_pretty_good_at_drawing/)  
[@TalentedJuli on Reddit](https://www.reddit.com/r/dalle2/comments/1712x7a/60s_pulp_magazine_illustration_is_the_best_style/)  
[@Wild-Culture-5068 on Reddit](https://www.reddit.com/r/dalle2/comments/17dwp0s/soviet_blade_runner/)  
[@popsicle_pope on Reddit](https://www.reddit.com/r/dalle2/comments/170lx1z/%F0%9D%94%AA%F0%9D%94%A2%F0%9D%94%B1%F0%9D%94%9E%F0%9D%94%AA%F0%9D%94%AC%F0%9D%94%AF%F0%9D%94%AD%F0%9D%94%A5%F0%9D%94%AC%F0%9D%94%B0%F0%9D%94%A6%F0%9D%94%B0/)  
[@gopatrik on Twitter](https://twitter.com/gopatrik/status/1717579802205626619)  
[@ARTiV3RSE on Twitter](https://twitter.com/ARTiV3RSE/status/1720202013638599040)  
[@willdepue on Twitter](https://twitter.com/willdepue/status/1705677997150445941)  
Various OpenAI employees

## Challenges

DALL·E-3 is still very new and there's still a lot of things it struggles with (or maybe I just haven't figured out how to prompt it correctly yet). Here's some challenges which you might want to try your hand at:

### Web Design

DALL·E really struggles at generating real looking websites, apps, etc. and often generates what looks like a portfolio page of a web designer. Here's the best I've gotten so far:

![websites](/images/dalle_3/websites.jpg)

### Seamless Textures

It feels like DALL·E-3 is so close to being able to generate seamless textures. Often they come out great, just slightly cutoff or with a few artifacts. See examples below:

![seamless](/images/dalle_3/seamless.jpg)

### Fonts

Using DALL·E to generate custom fonts or iterate on letter designs could be really cool, but I haven't been able to get it to work yet. Here's the best I've gotten so far:

![fonts](/images/dalle_3/fonts.jpg)

## More Resources

Thanks for reading! If you're looking for more resources on DALL·E-3, here are some related links:

- [DALL·E-3 Blog Post](https://openai.com/dall-e-3)
- [DALL·E-3 Research Paper](https://cdn.openai.com/papers/dall-e-3.pdf)
- [Image API Documentation](https://platform.openai.com/docs/api-reference/images)
- [Image API Cookbook](https://cookbook.openai.com/examples/dalle/image_generations_edits_and_variations_with_dall-e)
